from django.shortcuts import render
from django.contrib import messages


def base(request):
    return render(request, "appparqueo/base.html")


def inicio(request):
    return render(request, 'appparqueo/index.html')
