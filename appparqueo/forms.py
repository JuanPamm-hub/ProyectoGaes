from django import forms


class LoginClienteForm(forms.Form):
    correo = forms.EmailField(
        label="Correo electrónico",
        widget=forms.EmailInput(
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