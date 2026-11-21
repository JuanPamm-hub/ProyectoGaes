from django.contrib import messages
from django.shortcuts import redirect, render

from .forms import LoginClienteForm
from .models import Cliente


def base(request):
    return render(request, "appparqueo/base.html")


def inicio(request):
    return render(request, "appparqueo/index.html")


def iniciar_sesion_cliente(request):
    error_mensaje = None

    if request.method == "POST":
        form = LoginClienteForm(request.POST)
        if form.is_valid():
            correo = form.cleaned_data["correo"].strip().lower()
            contrasena = form.cleaned_data["contrasena"]
            recordar = form.cleaned_data["recordar"]

            cliente = Cliente.objects.filter(correo__iexact=correo).first()

            if cliente and cliente.activo and cliente.verificar_contrasena(contrasena):
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
