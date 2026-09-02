from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render

from .forms import LoginForm, SignupForm
from django.utils.translation import gettext as _


class ChalaaniLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class ChalaaniLogoutView(LogoutView):
    pass


def signup(request):
    if request.user.is_authenticated:
        return redirect("chalani:dashboard")
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, _("Welcome! Now upload a photo of your first chalani."))
            return redirect("chalani:dashboard")
    else:
        form = SignupForm()
    return render(request, "accounts/signup.html", {"form": form})
