from django import forms
from .models import Cliente


class LoginClienteForm(forms.Form):
    correo = forms.CharField(
        max_length=120,
        label="Correo electrónico",
        widget=forms.TextInput(
            attrs={
                "id": "correo",
                "class": "form-input",
                "placeholder": "tu-correo@ejemplo.com",
            }
        ),
    )
    contrasena = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(
            attrs={
                "id": "contrasena",
                "class": "form-input",
                "placeholder": "Ingresa tu contraseña",
            }
        ),
    )
    recordar = forms.BooleanField(required=False)


class RegistroClienteForm(forms.Form):
    nombre = forms.CharField(
        label="Nombre",
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "id": "nombre",
                "placeholder": "Tu nombre",
                "required": True,
            }
        ),
    )
    apellido = forms.CharField(
        label="Apellido",
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "id": "apellido",
                "placeholder": "Tu apellido",
                "required": True,
            }
        ),
    )
    documento = forms.CharField(
        label="Documento de identidad",
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "id": "documento",
                "placeholder": "Número de documento",
                "required": True,
            }
        ),
    )
    correo = forms.EmailField(
        label="Correo electrónico",
        max_length=120,
        widget=forms.EmailInput(
            attrs={
                "id": "correo",
                "placeholder": "correo@ejemplo.com",
                "required": True,
            }
        ),
    )
    telefono = forms.CharField(
        label="Teléfono / Celular",
        max_length=20,
        required=False,
        widget=forms.TextInput(
            attrs={
                "id": "telefono",
                "placeholder": "300 000 0000",
            }
        ),
    )
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(
            attrs={
                "id": "password",
                "placeholder": "Crea una contraseña",
                "required": True,
            }
        ),
    )
    password_confirm = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(
            attrs={
                "id": "password_confirm",
                "placeholder": "Repite la contraseña",
                "required": True,
            }
        ),
    )

    def clean_documento(self):
        documento = self.cleaned_data["documento"].strip()
        if Cliente.objects.filter(documento=documento).exists():
            raise forms.ValidationError("Ya existe un cliente registrado con este documento.")
        return documento

    def clean_correo(self):
        correo = self.cleaned_data["correo"].strip().lower()
        if Cliente.objects.filter(correo__iexact=correo).exists():
            raise forms.ValidationError("Ya existe una cuenta registrada con este correo electrónico.")
        return correo

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password and password_confirm and password != password_confirm:
            self.add_error("password_confirm", "Las contraseñas no coinciden.")

        return cleaned_data