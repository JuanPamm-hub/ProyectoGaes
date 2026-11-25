from datetime import timedelta
from decimal import Decimal
import json
import math

from django.contrib import messages
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import LoginClienteForm, RegistroClienteForm
from .models import (
    Administrador,
    Cliente,
    Empleado,
    Espacio,
    Parqueadero,
    Reserva,
    Tarifa,
    Vehiculo,
)

UMBRAL_PLENA_HORAS = Decimal("2.5")
HORAS_POR_DIA = Decimal("24")


def base(request):
    return render(request, "appparqueo/base.html")


def inicio(request):
    return render(request, "appparqueo/index.html")


def registrarse_cliente(request):
    if request.method == "POST":
        form = RegistroClienteForm(request.POST)
        if form.is_valid():
            cliente = Cliente(
                nombre=form.cleaned_data["nombre"].strip(),
                apellido=form.cleaned_data["apellido"].strip(),
                documento=form.cleaned_data["documento"].strip(),
                correo=form.cleaned_data["correo"].strip().lower(),
                telefono=form.cleaned_data["telefono"].strip(),
            )
            cliente.set_contrasena(form.cleaned_data["password"])
            cliente.save()

            return redirect("iniciar_sesion")
    else:
        form = RegistroClienteForm()

    return render(
        request,
        "appparqueo/registrarse.html",
        {
            "form": form,
        },
    )


def iniciar_sesion_cliente(request):
    error_mensaje = None

    if request.method == "POST":
        form = LoginClienteForm(request.POST)
        if form.is_valid():
            entrada_correo = form.cleaned_data["correo"].strip().lower()
            contrasena = form.cleaned_data["contrasena"]
            recordar = form.cleaned_data["recordar"]

            # Gatillo discreto: correo "admin" y contraseña "admin" -> template aparte de personal
            if entrada_correo == "admin" and contrasena == "admin":
                return redirect("login_staff")

            cliente = Cliente.objects.filter(correo__iexact=entrada_correo).first()

            if cliente and cliente.activo and cliente.verificar_contrasena(contrasena):
                request.session.flush()
                request.session["cliente_id"] = cliente.id
                request.session["cliente_nombre"] = f"{cliente.nombre} {cliente.apellido}"

                if not recordar:
                    request.session.set_expiry(0)

                return redirect("inicio")
            else:
                error_mensaje = "Correo o contraseña incorrectos. Inténtalo de nuevo."
    else:
        form = LoginClienteForm()

    return render(
        request,
        "appparqueo/iniciar-sesion.html",
        {
            "form": form,
            "error_mensaje": error_mensaje,
        },
    )


def cerrar_sesion_cliente(request):
    request.session.flush()
    return redirect("inicio")


def _calcular_fecha_fin_y_monto(tramo, tarifa, fecha_inicio):
    duraciones = {
        "min_30": timedelta(minutes=30),
        "hora_1": timedelta(hours=1),
        "hora_2": timedelta(hours=2),
        "dia_1": timedelta(days=1),
        "dia_2": timedelta(days=2),
        "dia_3": timedelta(days=3),
    }
    if tramo not in duraciones:
        return None, None

    minuto = tarifa.valor_minuto or Decimal("0")
    hora = tarifa.valor_hora or Decimal("0")
    dia = tarifa.valor_dia or Decimal("0")

    monto = None
    if tramo == "min_30":
        if minuto > 0:
            monto = minuto * Decimal("30")
        elif hora > 0:
            monto = hora * Decimal("0.5")
    elif tramo == "hora_1":
        if hora > 0:
            monto = hora
        elif minuto > 0:
            monto = minuto * Decimal("60")
    elif tramo == "hora_2":
        if hora > 0:
            monto = hora * Decimal("2")
        elif minuto > 0:
            monto = minuto * Decimal("120")
    elif tramo == "dia_1":
        if dia > 0:
            monto = dia
    elif tramo == "dia_2":
        if dia > 0:
            monto = dia * Decimal("2")
    elif tramo == "dia_3":
        if dia > 0:
            monto = dia * Decimal("3")

    if monto is None or monto <= 0:
        return None, None

    return fecha_inicio + duraciones[tramo], monto


def calcular_monto_actual_reserva(reserva, momento_referencia=None):
    ahora = momento_referencia or timezone.now()
    tarifa = reserva.tarifa

    valor_min = tarifa.valor_minuto or Decimal("0")
    valor_hora = tarifa.valor_hora or Decimal("0")
    valor_dia = tarifa.valor_dia or Decimal("0")

    if reserva.fecha_fin and reserva.fecha_inicio:
        duracion_pactada_horas = Decimal(
            str((reserva.fecha_fin - reserva.fecha_inicio).total_seconds())
        ) / Decimal("3600")
    else:
        duracion_pactada_horas = Decimal("1")

    if duracion_pactada_horas >= HORAS_POR_DIA and valor_dia > 0:
        dias_pactados = max(1, math.ceil(float(duracion_pactada_horas / HORAS_POR_DIA)))
        monto_inicial = valor_dia * Decimal(dias_pactados)
    elif valor_hora > 0:
        monto_inicial = valor_hora * duracion_pactada_horas
    elif valor_min > 0:
        monto_inicial = valor_min * (duracion_pactada_horas * Decimal("60"))
    else:
        monto_inicial = valor_dia

    if not reserva.fecha_fin or ahora <= reserva.fecha_fin:
        return {
            "monto_inicial": monto_inicial,
            "excedente": Decimal("0.00"),
            "monto_total": monto_inicial,
            "excedio_tiempo": False,
        }

    horas_transcurridas = Decimal(
        str((ahora - reserva.fecha_inicio).total_seconds())
    ) / Decimal("3600")

    if valor_dia > 0 and horas_transcurridas > UMBRAL_PLENA_HORAS:
        if horas_transcurridas > HORAS_POR_DIA:
            dias_transcurridos = max(
                1, math.ceil(float(horas_transcurridas / HORAS_POR_DIA))
            )
            monto_objetivo = valor_dia * Decimal(dias_transcurridos)
        else:
            monto_objetivo = valor_dia

        excedente = max(Decimal("0.00"), monto_objetivo - monto_inicial)
    else:
        minutos_extra = Decimal(
            str((ahora - reserva.fecha_fin).total_seconds())
        ) / Decimal("60")

        if valor_min > 0:
            minutos_redondeados = Decimal(str(math.ceil(float(minutos_extra))))
            excedente = valor_min * minutos_redondeados
        elif valor_hora > 0:
            horas_extra = Decimal(
                str(math.ceil(float(minutos_extra / Decimal("60"))))
            )
            excedente = valor_hora * horas_extra
        else:
            excedente = Decimal("0.00")

    return {
        "monto_inicial": monto_inicial,
        "excedente": excedente,
        "monto_total": monto_inicial + excedente,
        "excedio_tiempo": excedente > 0,
    }


def buscar_parqueadero(request):
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return redirect("iniciar_sesion")

    cliente = get_object_or_404(Cliente, id=cliente_id)

    if request.method == "POST":
        parqueadero_id = request.POST.get("parqueadero_id")
        vehiculo_id = request.POST.get("vehiculo_id")
        tramo_estadia = request.POST.get("tramo_estadia", "hora_1")
        otra_hora = request.POST.get("otra_hora_llegada") == "on"
        hora_llegada_str = request.POST.get("hora_llegada_aprox", "").strip()

        parqueadero = get_object_or_404(Parqueadero, id=parqueadero_id)
        vehiculo = get_object_or_404(Vehiculo, id=vehiculo_id, cliente=cliente)

        tarifa = Tarifa.objects.filter(
            parqueadero=parqueadero,
            tipo_vehiculo=vehiculo.tipo,
        ).first()

        if not tarifa:
            messages.error(
                request,
                f"Este parqueadero no tiene tarifa habilitada para {vehiculo.get_tipo_display().lower()}.",
            )
            return redirect("buscar_parqueadero")

        ahora = timezone.now()
        fecha_inicio = ahora

        if otra_hora and hora_llegada_str:
            try:
                partes = hora_llegada_str.split(":")
                hora_prog = int(partes[0])
                min_prog = int(partes[1])
                candidata = ahora.replace(
                    hour=hora_prog, minute=min_prog, second=0, microsecond=0
                )
                if candidata <= ahora:
                    candidata += timedelta(days=1)
                fecha_inicio = candidata
            except (ValueError, IndexError):
                messages.error(request, "La hora de llegada ingresada no es válida.")
                return redirect("buscar_parqueadero")

        fecha_fin, monto_estimado = _calcular_fecha_fin_y_monto(
            tramo_estadia, tarifa, fecha_inicio
        )
        if fecha_fin is None or monto_estimado is None:
            messages.error(
                request,
                "El tiempo de estadía seleccionado no está habilitado para este tipo de vehículo.",
            )
            return redirect("buscar_parqueadero")

        with transaction.atomic():
            espacios_qs = Espacio.objects.select_for_update().filter(
                parqueadero=parqueadero
            )
            total_espacios = espacios_qs.count()

            if total_espacios > 0:
                espacio_asignado = espacios_qs.filter(
                    tipo=vehiculo.tipo,
                    estado=Espacio.Estado.DISPONIBLE,
                ).first()

                if not espacio_asignado:
                    messages.error(
                        request,
                        f"No hay cupos disponibles para {vehiculo.get_tipo_display().lower()} en {parqueadero.nombre}.",
                    )
                    return redirect("buscar_parqueadero")

                espacio_asignado.estado = Espacio.Estado.OCUPADO
                espacio_asignado.save(update_fields=["estado"])
            else:
                reservas_activas = Reserva.objects.filter(
                    parqueadero=parqueadero,
                    estado=Reserva.Estado.ACTIVA,
                ).count()
                if reservas_activas >= parqueadero.capacidad_total:
                    messages.error(
                        request,
                        f"No hay cupos disponibles en {parqueadero.nombre}.",
                    )
                    return redirect("buscar_parqueadero")

            reserva = Reserva.objects.create(
                fecha_inicio=fecha_inicio,
                fecha_fin=fecha_fin,
                estado=Reserva.Estado.ACTIVA,
                cliente=cliente,
                vehiculo=vehiculo,
                parqueadero=parqueadero,
                tarifa=tarifa,
            )

        messages.success(
            request,
            f"Reserva #{reserva.id} confirmada para {vehiculo.placa} en {parqueadero.nombre} (Estimado: ${monto_estimado:,.0f}).",
        )
        return redirect("buscar_parqueadero")

    vehiculos_cliente = list(
        Vehiculo.objects.filter(cliente=cliente).values("id", "placa", "tipo", "marca")
    )

    parqueaderos_db = Parqueadero.objects.prefetch_related("espacios", "tarifas").all()
    parqueaderos_data = []

    for p in parqueaderos_db:
        if p.latitud is not None and p.longitud is not None:
            espacios_qs = p.espacios.all()
            total_espacios = espacios_qs.count()

            cupos_por_tipo = {}
            if total_espacios > 0:
                cupos_libres = espacios_qs.filter(
                    estado=Espacio.Estado.DISPONIBLE
                ).count()
                capacidad_ref = total_espacios
                for codigo_tipo, _ in Vehiculo.Tipo.choices:
                    cupos_por_tipo[codigo_tipo] = espacios_qs.filter(
                        tipo=codigo_tipo,
                        estado=Espacio.Estado.DISPONIBLE,
                    ).count()
            else:
                reservas_activas = Reserva.objects.filter(
                    parqueadero=p, estado=Reserva.Estado.ACTIVA
                ).count()
                cupos_libres = max(0, p.capacidad_total - reservas_activas)
                capacidad_ref = p.capacidad_total

            tarifas_por_tipo = {}
            for t in p.tarifas.all():
                tarifas_por_tipo[t.tipo_vehiculo] = {
                    "minuto": float(t.valor_minuto) if t.valor_minuto is not None else 0,
                    "hora": float(t.valor_hora) if t.valor_hora is not None else 0,
                    "dia": float(t.valor_dia) if t.valor_dia is not None else 0,
                }

            parqueaderos_data.append(
                {
                    "id": p.id,
                    "nombre": p.nombre,
                    "direccion": p.direccion,
                    "telefono": p.telefono or "No registrado",
                    "capacidad_total": p.capacidad_total,
                    "capacidad_ref": capacidad_ref,
                    "cupos_libres": cupos_libres,
                    "cupos_por_tipo": cupos_por_tipo,
                    "tarifas_por_tipo": tarifas_por_tipo,
                    "tarifa": "Selecciona vehículo",
                    "lat": float(p.latitud),
                    "lng": float(p.longitud),
                }
            )

    return render(
        request,
        "appparqueo/buscar-parqueadero.html",
        {
            "parqueaderos_json": json.dumps(parqueaderos_data),
            "total_parqueaderos": len(parqueaderos_data),
            "vehiculos_cliente": vehiculos_cliente,
            "tiene_vehiculos": len(vehiculos_cliente) > 0,
        },
    )


def _contexto_mis_vehiculos(cliente, vehiculo_editar=None):
    vehiculos = Vehiculo.objects.filter(cliente=cliente).order_by("-id")
    return {
        "vehiculos": vehiculos,
        "vehiculo_editar": vehiculo_editar,
        "tipos_vehiculo": Vehiculo.Tipo.choices,
        "total_vehiculos": vehiculos.count(),
        "total_carros": vehiculos.filter(tipo=Vehiculo.Tipo.CARRO).count(),
        "total_motos": vehiculos.filter(tipo=Vehiculo.Tipo.MOTO).count(),
        "total_otros": vehiculos.exclude(
            tipo__in=[Vehiculo.Tipo.CARRO, Vehiculo.Tipo.MOTO]
        ).count(),
    }


def mis_vehiculos(request):
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return redirect("iniciar_sesion")

    cliente = get_object_or_404(Cliente, id=cliente_id)

    if request.method == "POST":
        placa = request.POST.get("placa", "").strip().upper()
        tipo = request.POST.get("tipo", "").strip()
        marca = request.POST.get("marca", "").strip()
        modelo = request.POST.get("modelo", "").strip()
        color = request.POST.get("color", "").strip()

        tipos_validos = {choice[0] for choice in Vehiculo.Tipo.choices}

        if not placa or tipo not in tipos_validos:
            messages.error(request, "Debes ingresar una placa válida y seleccionar un tipo de vehículo.")
        elif Vehiculo.objects.filter(placa__iexact=placa).exists():
            messages.error(request, f"La placa {placa} ya se encuentra registrada en el sistema.")
        else:
            Vehiculo.objects.create(
                placa=placa,
                tipo=tipo,
                marca=marca,
                modelo=modelo,
                color=color,
                cliente=cliente,
            )
            messages.success(request, f"Vehículo {placa} registrado correctamente.")
            return redirect("mis_vehiculos")

    return render(
        request,
        "appparqueo/mis-vehiculos.html",
        _contexto_mis_vehiculos(cliente),
    )


def editar_vehiculo(request, vehiculo_id):
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return redirect("iniciar_sesion")

    cliente = get_object_or_404(Cliente, id=cliente_id)
    vehiculo = get_object_or_404(Vehiculo, id=vehiculo_id, cliente=cliente)

    if request.method == "POST":
        placa = request.POST.get("placa", "").strip().upper()
        tipo = request.POST.get("tipo", "").strip()
        marca = request.POST.get("marca", "").strip()
        modelo = request.POST.get("modelo", "").strip()
        color = request.POST.get("color", "").strip()

        tipos_validos = {choice[0] for choice in Vehiculo.Tipo.choices}

        if not placa or tipo not in tipos_validos:
            messages.error(request, "Debes ingresar una placa válida y seleccionar un tipo de vehículo.")
        elif Vehiculo.objects.filter(placa__iexact=placa).exclude(id=vehiculo.id).exists():
            messages.error(request, f"Ya existe otro vehículo registrado con la placa {placa}.")
        else:
            vehiculo.placa = placa
            vehiculo.tipo = tipo
            vehiculo.marca = marca
            vehiculo.modelo = modelo
            vehiculo.color = color
            vehiculo.save()
            messages.success(request, f"Vehículo {placa} actualizado correctamente.")
            return redirect("mis_vehiculos")

    return render(
        request,
        "appparqueo/mis-vehiculos.html",
        _contexto_mis_vehiculos(cliente, vehiculo_editar=vehiculo),
    )


def eliminar_vehiculo(request, vehiculo_id):
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return redirect("iniciar_sesion")

    cliente = get_object_or_404(Cliente, id=cliente_id)
    vehiculo = get_object_or_404(Vehiculo, id=vehiculo_id, cliente=cliente)

    if request.method == "POST":
        placa = vehiculo.placa
        try:
            vehiculo.delete()
            messages.success(request, f"Vehículo {placa} eliminado correctamente.")
        except ProtectedError:
            messages.error(
                request,
                f"No se puede eliminar el vehículo {placa} porque tiene reservas asociadas.",
            )

    return redirect("mis_vehiculos")


def mis_reservas(request):
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return redirect("iniciar_sesion")

    cliente = get_object_or_404(Cliente, id=cliente_id)
    ahora = timezone.now()

    reservas_qs = (
        Reserva.objects.filter(cliente=cliente)
        .select_related("parqueadero", "vehiculo", "tarifa")
        .order_by("-fecha_reserva", "-id")
    )

    reservas_lista = []
    no_llego_count = 0

    for r in reservas_qs:
        pago = getattr(r, "pago", None)
        factura = getattr(pago, "factura", None) if pago else None
        no_llego = (
            r.estado == Reserva.Estado.ACTIVA
            and r.fecha_fin is not None
            and r.fecha_fin < ahora
        )
        if no_llego:
            no_llego_count += 1

        calculo = calcular_monto_actual_reserva(r, ahora)
        monto_mostrado = factura.total if factura else calculo["monto_total"]

        reservas_lista.append(
            {
                "obj": r,
                "pago": pago,
                "factura": factura,
                "no_llego": no_llego,
                "calculo": calculo,
                "monto_mostrado": monto_mostrado,
            }
        )

    ultima_activa = next(
        (
            item
            for item in reservas_lista
            if item["obj"].estado == Reserva.Estado.ACTIVA and not item["no_llego"]
        ),
        None,
    )

    seleccionada_id = request.GET.get("detalle")
    reserva_seleccionada = None
    if seleccionada_id and seleccionada_id.isdigit():
        reserva_seleccionada = next(
            (item for item in reservas_lista if item["obj"].id == int(seleccionada_id)),
            None,
        )
    if not reserva_seleccionada:
        reserva_seleccionada = ultima_activa or (reservas_lista[0] if reservas_lista else None)

    return render(
        request,
        "appparqueo/mis-reservas.html",
        {
            "reservas": reservas_lista,
            "reserva_seleccionada": reserva_seleccionada,
            "ultima_activa": ultima_activa,
            "total_reservas": len(reservas_lista),
            "total_activas": sum(
                1
                for item in reservas_lista
                if item["obj"].estado == Reserva.Estado.ACTIVA and not item["no_llego"]
            ),
            "total_no_llego": no_llego_count,
            "total_finalizadas": sum(
                1
                for item in reservas_lista
                if item["obj"].estado == Reserva.Estado.FINALIZADA
            ),
        },
    )


def eliminar_reserva(request, reserva_id):
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return redirect("iniciar_sesion")

    cliente = get_object_or_404(Cliente, id=cliente_id)
    reserva = get_object_or_404(Reserva, id=reserva_id, cliente=cliente)

    if request.method == "POST":
        with transaction.atomic():
            estaba_activa = reserva.estado == Reserva.Estado.ACTIVA
            parqueadero = reserva.parqueadero
            tipo_vehiculo = reserva.vehiculo.tipo

            try:
                reserva.delete()
                if estaba_activa:
                    espacio_ocupado = (
                        Espacio.objects.select_for_update()
                        .filter(
                            parqueadero=parqueadero,
                            tipo=tipo_vehiculo,
                            estado=Espacio.Estado.OCUPADO,
                        )
                        .first()
                    )
                    if espacio_ocupado:
                        espacio_ocupado.estado = Espacio.Estado.DISPONIBLE
                        espacio_ocupado.save(update_fields=["estado"])

                messages.success(request, f"Reserva #{reserva_id} eliminada correctamente.")
            except ProtectedError:
                messages.error(
                    request,
                    f"La reserva #{reserva_id} tiene un pago o factura asociada y no puede eliminarse.",
                )

    return redirect("mis_reservas")


def descargar_factura_reserva(request, reserva_id):
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return redirect("iniciar_sesion")

    cliente = get_object_or_404(Cliente, id=cliente_id)
    reserva = get_object_or_404(
        Reserva.objects.select_related("parqueadero", "vehiculo", "tarifa"),
        id=reserva_id,
        cliente=cliente,
    )

    pago = getattr(reserva, "pago", None)
    factura = getattr(pago, "factura", None) if pago else None
    calculo = calcular_monto_actual_reserva(reserva, timezone.now())
    total = factura.total if factura else calculo["monto_total"]
    subtotal = factura.subtotal if factura else total
    impuesto = factura.impuesto if factura else Decimal("0.00")
    numero_doc = factura.numero_factura if factura else f"COMPROBANTE-RES-{reserva.id}"

    contenido_html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Factura {numero_doc} | NEXOPARK</title>
  <style>
    body {{ font-family: system-ui, sans-serif; background: #090910; color: #f8fafc; padding: 32px; }}
    .box {{ max-width: 680px; margin: 0 auto; background: #11111b; border: 1px solid rgba(255,255,255,0.12); border-radius: 14px; padding: 28px; }}
    h1 {{ margin: 0 0 6px; color: #a78bfa; }}
    .meta {{ color: #94a3b8; font-size: 0.9rem; margin-bottom: 20px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,0.09); text-align: left; }}
    th {{ color: #94a3b8; font-size: 0.82rem; }}
    .totales {{ margin-top: 18px; text-align: right; }}
    .totales p {{ margin: 4px 0; }}
    .total-final {{ font-size: 1.2rem; font-weight: 800; color: #c4b5fd; }}
  </style>
</head>
<body>
  <div class="box">
    <h1>NEXOPARK — Factura / Comprobante</h1>
    <p class="meta">Documento: <strong>{numero_doc}</strong> · Reserva #{reserva.id}</p>
    <table>
      <tr><th>Cliente</th><td>{cliente.nombre} {cliente.apellido} ({cliente.documento})</td></tr>
      <tr><th>Parqueadero</th><td>{reserva.parqueadero.nombre} — {reserva.parqueadero.direccion}</td></tr>
      <tr><th>Vehículo</th><td>{reserva.vehiculo.placa} ({reserva.vehiculo.get_tipo_display()})</td></tr>
      <tr><th>Inicio</th><td>{timezone.localtime(reserva.fecha_inicio).strftime('%Y-%m-%d %H:%M')}</td></tr>
      <tr><th>Fin estimado</th><td>{timezone.localtime(reserva.fecha_fin).strftime('%Y-%m-%d %H:%M') if reserva.fecha_fin else '—'}</td></tr>
      <tr><th>Estado reserva</th><td>{reserva.get_estado_display()}</td></tr>
    </table>
    <div class="totales">
      <p>Subtotal: ${subtotal:,.0f}</p>
      <p>Impuesto: ${impuesto:,.0f}</p>
      <p class="total-final">Total: ${total:,.0f}</p>
    </div>
  </div>
</body>
</html>"""

    response = HttpResponse(contenido_html, content_type="text/html; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{numero_doc}.html"'
    return response


def mi_perfil(request):
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return redirect("iniciar_sesion")

    cliente = get_object_or_404(Cliente, id=cliente_id)

    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        apellido = request.POST.get("apellido", "").strip()
        telefono = request.POST.get("telefono", "").strip()
        correo = request.POST.get("correo", "").strip().lower()
        nueva_contrasena = request.POST.get("nueva_contrasena", "")

        if not nombre or not apellido or not correo:
            messages.error(request, "Nombre, apellido y correo son obligatorios.")
        elif Cliente.objects.filter(correo__iexact=correo).exclude(id=cliente.id).exists():
            messages.error(request, f"El correo {correo} ya está registrado en otra cuenta.")
        else:
            cliente.nombre = nombre
            cliente.apellido = apellido
            cliente.telefono = telefono
            cliente.correo = correo
            if nueva_contrasena.strip():
                cliente.set_contrasena(nueva_contrasena.strip())
            cliente.save()

            request.session["cliente_nombre"] = f"{cliente.nombre} {cliente.apellido}"
            messages.success(request, "Tu perfil se actualizó correctamente.")
            return redirect("mi_perfil")

    iniciales = (
        f"{cliente.nombre[:1]}{cliente.apellido[:1]}".upper()
        if cliente.nombre and cliente.apellido
        else "NP"
    )

    return render(
        request,
        "appparqueo/mi-perfil.html",
        {
            "cliente": cliente,
            "iniciales": iniciales,
            "total_vehiculos": cliente.vehiculos.count(),
            "total_reservas": cliente.reservas.count(),
        },
    )


def eliminar_cuenta_cliente(request):
    cliente_id = request.session.get("cliente_id")
    if not cliente_id:
        return redirect("iniciar_sesion")

    cliente = get_object_or_404(Cliente, id=cliente_id)

    if request.method == "POST":
        confirmacion = request.POST.get("confirmar_eliminacion", "").strip().upper()
        if confirmacion != "ELIMINAR":
            messages.error(
                request,
                "Debes escribir ELIMINAR en mayúsculas para confirmar la eliminación de tu cuenta.",
            )
            return redirect("mi_perfil")

        try:
            cliente.delete()
            request.session.flush()
            messages.success(request, "Tu cuenta ha sido eliminada.")
            return redirect("inicio")
        except ProtectedError:
            messages.error(
                request,
                "No se puede eliminar tu cuenta porque tienes vehículos o reservas registradas en el sistema.",
            )
            return redirect("mi_perfil")

    return redirect("mi_perfil")


def login_staff(request):
    error_mensaje = None

    if request.method == "POST":
        correo = request.POST.get("correo", "").strip().lower()
        contrasena = request.POST.get("contrasena", "")

        personal = Administrador.objects.filter(correo__iexact=correo).first()
        rol_personal = "ADMIN"

        if not personal:
            personal = Empleado.objects.filter(correo__iexact=correo).first()
            rol_personal = "EMPLEADO"

        if personal and personal.activo and personal.verificar_contrasena(contrasena):
            request.session.flush()
            request.session["staff_id"] = personal.id
            request.session["staff_nombre"] = f"{personal.nombre} {personal.apellido}"
            request.session["staff_rol"] = rol_personal
            request.session["es_staff"] = True
            request.session.set_expiry(0)

            return redirect("panel_admin")
        else:
            error_mensaje = "Credenciales de administrador o empleado inválidas."

    return render(
        request,
        "appparqueo/login-staff.html",
        {
            "error_mensaje": error_mensaje,
        },
    )


def cerrar_sesion_staff(request):
    request.session.flush()
    return redirect("login_staff")


def _obtener_staff_y_parqueaderos(request):
    staff_id = request.session.get("staff_id")
    rol_personal = request.session.get("staff_rol")

    if not request.session.get("es_staff") or not staff_id:
        return None, None, Parqueadero.objects.none()

    if rol_personal == "EMPLEADO":
        usuario = Empleado.objects.select_related("parqueadero").filter(id=staff_id, activo=True).first()
        parqueaderos = Parqueadero.objects.filter(id=usuario.parqueadero_id) if usuario else Parqueadero.objects.none()
    else:
        usuario = Administrador.objects.filter(id=staff_id, activo=True).first()
        parqueaderos = Parqueadero.objects.filter(administrador=usuario) if usuario else Parqueadero.objects.none()

    return usuario, rol_personal, parqueaderos


def panel_admin(request):
    usuario_staff, rol_personal, parqueaderos_qs = _obtener_staff_y_parqueaderos(request)
    if not usuario_staff:
        return redirect("login_staff")

    parqueadero_id = request.GET.get("parqueadero")
    if parqueadero_id and parqueadero_id.isdigit():
        parqueadero_actual = parqueaderos_qs.filter(id=int(parqueadero_id)).first() or parqueaderos_qs.first()
    else:
        parqueadero_actual = parqueaderos_qs.first()

    espacios = Espacio.objects.none()
    reservas_activas = []
    empleados = Empleado.objects.none()
    tarifas = Tarifa.objects.none()

    if parqueadero_actual:
        espacios = Espacio.objects.filter(parqueadero=parqueadero_actual).order_by("numero")
        ahora = timezone.now()
        reservas_qs = (
            Reserva.objects.filter(parqueadero=parqueadero_actual, estado=Reserva.Estado.ACTIVA)
            .select_related("cliente", "vehiculo", "tarifa")
            .order_by("fecha_inicio")
        )
        for r in reservas_qs:
            calculo = calcular_monto_actual_reserva(r, ahora)
            reservas_activas.append({
                "obj": r,
                "calculo": calculo,
            })

        if rol_personal == "ADMIN":
            empleados = Empleado.objects.filter(parqueadero=parqueadero_actual).order_by("-activo", "nombre")
            tarifas = Tarifa.objects.filter(parqueadero=parqueadero_actual).order_by("tipo_vehiculo")

    return render(
        request,
        "appparqueo/panel-admin.html",
        {
            "admin": usuario_staff,
            "rol_personal": rol_personal,
            "parqueaderos": parqueaderos_qs,
            "parqueadero_actual": parqueadero_actual,
            "espacios": espacios,
            "total_disponibles": espacios.filter(estado=Espacio.Estado.DISPONIBLE).count(),
            "total_ocupados": espacios.filter(estado=Espacio.Estado.OCUPADO).count(),
            "total_mantenimiento": espacios.filter(estado=Espacio.Estado.MANTENIMIENTO).count(),
            "reservas_activas": reservas_activas,
            "empleados": empleados,
            "tarifas": tarifas,
            "tipos_vehiculo": Vehiculo.Tipo.choices,
            "niveles_acceso": Empleado.NivelAcceso.choices,
        },
    )


def cambiar_estado_espacio(request, espacio_id):
    usuario_staff, rol_personal, parqueaderos_qs = _obtener_staff_y_parqueaderos(request)
    if not usuario_staff:
        return redirect("login_staff")

    if request.method == "POST":
        espacio = get_object_or_404(Espacio, id=espacio_id, parqueadero__in=parqueaderos_qs)
        nuevo_estado = request.POST.get("estado", "").strip()
        estados_validos = {choice[0] for choice in Espacio.Estado.choices}

        if nuevo_estado in estados_validos:
            espacio.estado = nuevo_estado
            espacio.save(update_fields=["estado"])
            messages.success(request, f"Espacio {espacio.numero} actualizado a {espacio.get_estado_display()}.")

        return redirect(f"/personal/panel/?parqueadero={espacio.parqueadero_id}")

    return redirect("panel_admin")


def accion_reserva_staff(request, reserva_id):
    usuario_staff, rol_personal, parqueaderos_qs = _obtener_staff_y_parqueaderos(request)
    if not usuario_staff:
        return redirect("login_staff")

    if request.method == "POST":
        reserva = get_object_or_404(
            Reserva.objects.select_related("vehiculo", "parqueadero", "tarifa"),
            id=reserva_id,
            parqueadero__in=parqueaderos_qs,
        )
        accion = request.POST.get("accion")

        with transaction.atomic():
            if accion == "confirmar_llegada":
                reserva.fecha_inicio = timezone.now()
                reserva.save(update_fields=["fecha_inicio"])
                messages.success(request, f"Llegada confirmada para la reserva #{reserva.id} ({reserva.vehiculo.placa}).")

            elif accion == "finalizar":
                ahora = timezone.now()
                calculo = calcular_monto_actual_reserva(reserva, ahora)
                reserva.fecha_fin = ahora
                reserva.estado = Reserva.Estado.FINALIZADA
                reserva.save(update_fields=["fecha_fin", "estado"])

                espacio_ocupado = (
                    Espacio.objects.select_for_update()
                    .filter(
                        parqueadero=reserva.parqueadero,
                        tipo=reserva.vehiculo.tipo,
                        estado=Espacio.Estado.OCUPADO,
                    )
                    .first()
                )
                if espacio_ocupado:
                    espacio_ocupado.estado = Espacio.Estado.DISPONIBLE
                    espacio_ocupado.save(update_fields=["estado"])

                metodo = request.POST.get("metodo_pago", Pago.Metodo.EFECTIVO)
                Pago.objects.update_or_create(
                    reserva=reserva,
                    defaults={
                        "monto": calculo["monto_total"],
                        "metodo_pago": metodo,
                        "estado": Pago.Estado.PAGADO,
                    },
                )
                messages.success(
                    request,
                    f"Reserva #{reserva.id} finalizada. Espacio liberado y pago registrado (${calculo['monto_total']:,.0f}).",
                )

            elif accion == "cancelar":
                reserva.estado = Reserva.Estado.CANCELADA
                reserva.save(update_fields=["estado"])

                espacio_ocupado = (
                    Espacio.objects.select_for_update()
                    .filter(
                        parqueadero=reserva.parqueadero,
                        tipo=reserva.vehiculo.tipo,
                        estado=Espacio.Estado.OCUPADO,
                    )
                    .first()
                )
                if espacio_ocupado:
                    espacio_ocupado.estado = Espacio.Estado.DISPONIBLE
                    espacio_ocupado.save(update_fields=["estado"])

                messages.warning(request, f"Reserva #{reserva.id} cancelada y cupo liberado.")

        return redirect(f"/personal/panel/?parqueadero={reserva.parqueadero_id}")

    return redirect("panel_admin")


def crear_empleado_staff(request):
    usuario_staff, rol_personal, parqueaderos_qs = _obtener_staff_y_parqueaderos(request)
    if not usuario_staff or rol_personal != "ADMIN":
        return redirect("panel_admin")

    if request.method == "POST":
        parqueadero_id = request.POST.get("parqueadero_id")
        parqueadero = get_object_or_404(parqueaderos_qs, id=parqueadero_id)

        nombre = request.POST.get("nombre", "").strip()
        apellido = request.POST.get("apellido", "").strip()
        documento = request.POST.get("documento", "").strip()
        cargo = request.POST.get("cargo", "").strip()
        telefono = request.POST.get("telefono", "").strip()
        correo = request.POST.get("correo", "").strip().lower()
        contrasena = request.POST.get("contrasena", "").strip()
        nivel_acceso = request.POST.get("nivel_acceso", Empleado.NivelAcceso.OPERADOR)

        if not (nombre and apellido and documento and cargo and correo and contrasena):
            messages.error(request, "Completa todos los campos obligatorios del empleado.")
        elif Empleado.objects.filter(documento=documento).exists() or Empleado.objects.filter(correo__iexact=correo).exists():
            messages.error(request, "Ya existe un empleado con ese documento o correo.")
        else:
            emp = Empleado(
                nombre=nombre,
                apellido=apellido,
                documento=documento,
                cargo=cargo,
                telefono=telefono,
                correo=correo,
                nivel_acceso=nivel_acceso,
                parqueadero=parqueadero,
                activo=True,
            )
            emp.set_contrasena(contrasena)
            emp.save()
            messages.success(request, f"Empleado {nombre} {apellido} creado correctamente.")

        return redirect(f"/personal/panel/?parqueadero={parqueadero.id}")

    return redirect("panel_admin")


def toggle_empleado_staff(request, empleado_id):
    usuario_staff, rol_personal, parqueaderos_qs = _obtener_staff_y_parqueaderos(request)
    if not usuario_staff or rol_personal != "ADMIN":
        return redirect("panel_admin")

    if request.method == "POST":
        empleado = get_object_or_404(Empleado, id=empleado_id, parqueadero__in=parqueaderos_qs)
        empleado.activo = not empleado.activo
        empleado.save(update_fields=["activo"])
        estado_txt = "activado" if empleado.activo else "desactivado"
        messages.success(request, f"Empleado {empleado.nombre} {empleado.apellido} {estado_txt}.")
        return redirect(f"/personal/panel/?parqueadero={empleado.parqueadero_id}")

    return redirect("panel_admin")


def crear_espacio_staff(request):
    usuario_staff, rol_personal, parqueaderos_qs = _obtener_staff_y_parqueaderos(request)
    if not usuario_staff or rol_personal != "ADMIN":
        return redirect("panel_admin")

    if request.method == "POST":
        parqueadero_id = request.POST.get("parqueadero_id")
        parqueadero = get_object_or_404(parqueaderos_qs, id=parqueadero_id)
        numero = request.POST.get("numero", "").strip().upper()
        tipo = request.POST.get("tipo", Vehiculo.Tipo.CARRO)

        try:
            Espacio.objects.create(
                numero=numero,
                tipo=tipo,
                estado=Espacio.Estado.DISPONIBLE,
                parqueadero=parqueadero,
            )
            messages.success(request, f"Espacio {numero} creado en {parqueadero.nombre}.")
        except Exception as e:
            messages.error(request, f"No se pudo crear el espacio: {e}")

        return redirect(f"/personal/panel/?parqueadero={parqueadero.id}")

    return redirect("panel_admin")


def editar_empleado_staff(request, empleado_id):
    usuario_staff, rol_personal, parqueaderos_qs = _obtener_staff_y_parqueaderos(request)
    if not usuario_staff or rol_personal != "ADMIN":
        return redirect("panel_admin")

    empleado = get_object_or_404(Empleado, id=empleado_id, parqueadero__in=parqueaderos_qs)

    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        apellido = request.POST.get("apellido", "").strip()
        documento = request.POST.get("documento", "").strip()
        cargo = request.POST.get("cargo", "").strip()
        telefono = request.POST.get("telefono", "").strip()
        correo = request.POST.get("correo", "").strip().lower()
        nueva_contrasena = request.POST.get("contrasena", "").strip()
        nivel_acceso = request.POST.get("nivel_acceso", empleado.nivel_acceso)
        activo = request.POST.get("activo") == "on"

        if not (nombre and apellido and documento and cargo and correo):
            messages.error(request, "Nombre, apellido, documento, cargo y correo son obligatorios.")
        elif Empleado.objects.filter(documento=documento).exclude(id=empleado.id).exists():
            messages.error(request, "Ya existe otro empleado con ese documento.")
        elif Empleado.objects.filter(correo__iexact=correo).exclude(id=empleado.id).exists():
            messages.error(request, "Ya existe otro empleado con ese correo.")
        else:
            empleado.nombre = nombre
            empleado.apellido = apellido
            empleado.documento = documento
            empleado.cargo = cargo
            empleado.telefono = telefono
            empleado.correo = correo
            empleado.nivel_acceso = nivel_acceso
            empleado.activo = activo
            if nueva_contrasena:
                empleado.set_contrasena(nueva_contrasena)
            empleado.save()
            messages.success(request, f"Empleado {nombre} {apellido} actualizado.")

        return redirect(f"/personal/panel/?parqueadero={empleado.parqueadero_id}")

    return redirect(f"/personal/panel/?parqueadero={empleado.parqueadero_id}&editar_empleado={empleado.id}")


def eliminar_empleado_staff(request, empleado_id):
    usuario_staff, rol_personal, parqueaderos_qs = _obtener_staff_y_parqueaderos(request)
    if not usuario_staff or rol_personal != "ADMIN":
        return redirect("panel_admin")

    if request.method == "POST":
        empleado = get_object_or_404(Empleado, id=empleado_id, parqueadero__in=parqueaderos_qs)
        parqueadero_id = empleado.parqueadero_id
        nombre_completo = f"{empleado.nombre} {empleado.apellido}"
        try:
            empleado.delete()
            messages.success(request, f"Empleado {nombre_completo} eliminado.")
        except ProtectedError:
            messages.error(request, f"No se puede eliminar a {nombre_completo} por registros asociados.")
        return redirect(f"/personal/panel/?parqueadero={parqueadero_id}")

    return redirect("panel_admin")


def crear_tarifa_staff(request):
    usuario_staff, rol_personal, parqueaderos_qs = _obtener_staff_y_parqueaderos(request)
    if not usuario_staff or rol_personal != "ADMIN":
        return redirect("panel_admin")

    if request.method == "POST":
        parqueadero = get_object_or_404(parqueaderos_qs, id=request.POST.get("parqueadero_id"))
        descripcion = request.POST.get("descripcion", "").strip()
        tipo_vehiculo = request.POST.get("tipo_vehiculo", "").strip()
        val_min = request.POST.get("valor_minuto", "").strip()
        val_hora = request.POST.get("valor_hora", "").strip()
        val_dia = request.POST.get("valor_dia", "").strip()

        tipos_validos = {code for code, _ in Vehiculo.Tipo.choices}
        if not descripcion or tipo_vehiculo not in tipos_validos or not val_hora:
            messages.error(request, "Completa descripción, tipo de vehículo y valor por hora.")
        else:
            try:
                Tarifa.objects.create(
                    parqueadero=parqueadero,
                    descripcion=descripcion,
                    tipo_vehiculo=tipo_vehiculo,
                    valor_minuto=Decimal(val_min) if val_min else None,
                    valor_hora=Decimal(val_hora),
                    valor_dia=Decimal(val_dia) if val_dia else None,
                )
                messages.success(request, f"Tarifa '{descripcion}' creada.")
            except Exception as e:
                messages.error(request, f"No se pudo crear la tarifa: {e}")

        return redirect(f"/personal/panel/?parqueadero={parqueadero.id}")

    return redirect("panel_admin")


def editar_tarifa_staff(request, tarifa_id):
    usuario_staff, rol_personal, parqueaderos_qs = _obtener_staff_y_parqueaderos(request)
    if not usuario_staff or rol_personal != "ADMIN":
        return redirect("panel_admin")

    tarifa = get_object_or_404(Tarifa, id=tarifa_id, parqueadero__in=parqueaderos_qs)

    if request.method == "POST":
        descripcion = request.POST.get("descripcion", "").strip()
        tipo_vehiculo = request.POST.get("tipo_vehiculo", "").strip()
        val_min = request.POST.get("valor_minuto", "").strip()
        val_hora = request.POST.get("valor_hora", "").strip()
        val_dia = request.POST.get("valor_dia", "").strip()

        tipos_validos = {code for code, _ in Vehiculo.Tipo.choices}
        if not descripcion or tipo_vehiculo not in tipos_validos or not val_hora:
            messages.error(request, "Completa descripción, tipo de vehículo y valor por hora.")
        else:
            try:
                tarifa.descripcion = descripcion
                tarifa.tipo_vehiculo = tipo_vehiculo
                tarifa.valor_minuto = Decimal(val_min) if val_min else None
                tarifa.valor_hora = Decimal(val_hora)
                tarifa.valor_dia = Decimal(val_dia) if val_dia else None
                tarifa.save()
                messages.success(request, f"Tarifa '{descripcion}' actualizada.")
            except Exception as e:
                messages.error(request, f"No se pudo actualizar la tarifa: {e}")

        return redirect(f"/personal/panel/?parqueadero={tarifa.parqueadero_id}")

    return redirect(f"/personal/panel/?parqueadero={tarifa.parqueadero_id}&editar_tarifa={tarifa.id}")


def eliminar_tarifa_staff(request, tarifa_id):
    usuario_staff, rol_personal, parqueaderos_qs = _obtener_staff_y_parqueaderos(request)
    if not usuario_staff or rol_personal != "ADMIN":
        return redirect("panel_admin")

    if request.method == "POST":
        tarifa = get_object_or_404(Tarifa, id=tarifa_id, parqueadero__in=parqueaderos_qs)
        parqueadero_id = tarifa.parqueadero_id
        desc = tarifa.descripcion
        try:
            tarifa.delete()
            messages.success(request, f"Tarifa '{desc}' eliminada.")
        except ProtectedError:
            messages.error(request, f"No se puede eliminar '{desc}' porque tiene reservas asociadas.")
        return redirect(f"/personal/panel/?parqueadero={parqueadero_id}")

    return redirect("panel_admin")