from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q


class Administrador(models.Model):
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    documento = models.CharField(max_length=20, unique=True)
    telefono = models.CharField(max_length=20, blank=True)
    correo = models.EmailField(max_length=120, unique=True)
    contrasena = models.CharField(max_length=255)

    class Meta:
        verbose_name = "administrador"
        verbose_name_plural = "administradores"

    def __str__(self):
        return f"{self.nombre} {self.apellido}"


class Parqueadero(models.Model):
    nombre = models.CharField(max_length=100)
    direccion = models.CharField(max_length=150)
    telefono = models.CharField(max_length=20, blank=True)
    capacidad_total = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    # Administrador 1 : N Parqueadero (TIENE)
    administrador = models.ForeignKey(
        Administrador, on_delete=models.PROTECT, related_name="parqueaderos"
    )

    def __str__(self):
        return self.nombre


class Cliente(models.Model):
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    documento = models.CharField(max_length=20, unique=True)
    telefono = models.CharField(max_length=20, blank=True)
    correo = models.EmailField(max_length=120, unique=True, null=True, blank=True)

    def __str__(self):
        return f"{self.nombre} {self.apellido}"


class Vehiculo(models.Model):
    class Tipo(models.TextChoices):
        CARRO = "CARRO", "Carro"
        MOTO = "MOTO", "Moto"
        BICICLETA = "BICICLETA", "Bicicleta"
        OTRO = "OTRO", "Otro"

    placa = models.CharField(max_length=10, unique=True)
    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    marca = models.CharField(max_length=50, blank=True)
    modelo = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=30, blank=True)
    # Cliente 1 : N Vehiculo (REGISTRA)
    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, related_name="vehiculos"
    )

    def __str__(self):
        return self.placa


class Tarifa(models.Model):
    descripcion = models.CharField(max_length=100)
    tipo_vehiculo = models.CharField(max_length=30, choices=Vehiculo.Tipo.choices)
    valor_hora = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )
    valor_dia = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    # Parqueadero 1 : N Tarifa (MANEJA)
    parqueadero = models.ForeignKey(
        Parqueadero, on_delete=models.PROTECT, related_name="tarifas"
    )

    def __str__(self):
        return f"{self.descripcion} ({self.tipo_vehiculo})"


class Espacio(models.Model):
    class Estado(models.TextChoices):
        DISPONIBLE = "DISPONIBLE", "Disponible"
        OCUPADO = "OCUPADO", "Ocupado"
        MANTENIMIENTO = "MANTENIMIENTO", "Mantenimiento"

    numero = models.CharField(max_length=10)
    tipo = models.CharField(max_length=30)
    estado = models.CharField(
        max_length=20, choices=Estado.choices, default=Estado.DISPONIBLE
    )
    # Parqueadero 1 : N Espacio (TIENE)
    parqueadero = models.ForeignKey(
        Parqueadero, on_delete=models.CASCADE, related_name="espacios"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["parqueadero", "numero"], name="uq_espacio_numero"
            )
        ]

    def __str__(self):
        return f"Espacio {self.numero} - {self.parqueadero}"


class Empleado(models.Model):
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    documento = models.CharField(max_length=20, unique=True)
    cargo = models.CharField(max_length=50)
    telefono = models.CharField(max_length=20, blank=True)
    # Parqueadero 1 : N Empleado (TRABAJA)
    parqueadero = models.ForeignKey(
        Parqueadero, on_delete=models.PROTECT, related_name="empleados"
    )

    def __str__(self):
        return f"{self.nombre} {self.apellido} - {self.cargo}"


class Reserva(models.Model):
    class Estado(models.TextChoices):
        ACTIVA = "ACTIVA", "Activa"
        FINALIZADA = "FINALIZADA", "Finalizada"
        CANCELADA = "CANCELADA", "Cancelada"

    fecha_reserva = models.DateTimeField(auto_now_add=True)
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(
        max_length=20, choices=Estado.choices, default=Estado.ACTIVA
    )
    # Cliente 1 : N Reserva (REALIZA)
    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, related_name="reservas"
    )
    # Vehiculo 1 : N Reserva (ASOCIA)
    vehiculo = models.ForeignKey(
        Vehiculo, on_delete=models.PROTECT, related_name="reservas"
    )
    # Parqueadero 1 : N Reserva (OCUPA)
    parqueadero = models.ForeignKey(
        Parqueadero, on_delete=models.PROTECT, related_name="reservas"
    )
    # Tarifa 1 : N Reserva (INCLUYE)
    tarifa = models.ForeignKey(
        Tarifa, on_delete=models.PROTECT, related_name="reservas"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(fecha_fin__isnull=True) | Q(fecha_fin__gt=F("fecha_inicio")),
                name="ck_reserva_fechas",
            )
        ]

    def __str__(self):
        return f"Reserva #{self.pk} - {self.cliente}"


class Pago(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        PAGADO = "PAGADO", "Pagado"
        ANULADO = "ANULADO", "Anulado"

    class Metodo(models.TextChoices):
        EFECTIVO = "EFECTIVO", "Efectivo"
        TARJETA = "TARJETA", "Tarjeta"
        TRANSFERENCIA = "TRANSFERENCIA", "Transferencia"

    fecha_pago = models.DateTimeField(auto_now_add=True)
    monto = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )
    metodo_pago = models.CharField(max_length=30, choices=Metodo.choices)
    estado = models.CharField(
        max_length=20, choices=Estado.choices, default=Estado.PENDIENTE
    )
    # Reserva 1 : 1 Pago (TIENE)
    reserva = models.OneToOneField(
        Reserva, on_delete=models.PROTECT, related_name="pago"
    )

    def __str__(self):
        return f"Pago #{self.pk} - {self.monto}"


class Factura(models.Model):
    numero_factura = models.CharField(max_length=30, unique=True)
    fecha_emision = models.DateTimeField(auto_now_add=True)
    subtotal = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )
    impuesto = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
    )
    total = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )
    # Pago 1 : 1 Factura (GENERA)
    pago = models.OneToOneField(
        Pago, on_delete=models.PROTECT, related_name="factura"
    )

    def __str__(self):
        return self.numero_factura