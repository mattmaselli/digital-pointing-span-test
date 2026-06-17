from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.models import User
from doctor.models import Doctor
from django.db import transaction

def home(request):
    return render(request, 'home.html')

def about(request):
    return render(request, 'about.html')

def login(request):
    if request.user.is_authenticated:
        return redirect('doctor:dashboard')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            return redirect('doctor:dashboard')
        return render(request, 'login.html', {'login_error': 'Invalid email or password.'})
    return render(request, 'login.html')

def register(request):
    if request.user.is_authenticated:
        return redirect('doctor:dashboard')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        confirm  = request.POST.get('confirm_password')
        if password != confirm:
            return render(request, 'register.html', {'register_error': 'Passwords do not match.'})
        if User.objects.filter(username=username).exists():
            return render(request, 'register.html', {'register_error': 'Account already exists.'})
        try:
            with transaction.atomic():
                user = User.objects.create_user(username=username, password=password)
                Doctor.objects.create(user=user)
        except Exception:
            return render(request, 'register.html', {'register_error': 'Something went wrong. Try again.'})
        auth_login(request, user)
        return redirect('doctor:dashboard')
    return render(request, 'register.html')

def logout(request):
    auth_logout(request)
    return redirect('home')