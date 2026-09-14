from django.http import JsonResponse
from django.shortcuts import render

from .models import Inquiry

REASON_VALUES = {value for value, _ in Inquiry.Reason.choices}


def contact(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
        reason = request.POST.get("reason", "").strip()
        message = request.POST.get("message", "").strip()

        errors = {}
        if not name:
            errors["name"] = "Please enter your name."
        if not email:
            errors["email"] = "Please enter your email address."
        if reason not in REASON_VALUES:
            errors["reason"] = "Please choose a reason for contact."
        if not message:
            errors["message"] = "Please enter a message."

        if errors:
            return JsonResponse({"ok": False, "errors": errors}, status=400)

        Inquiry.objects.create(name=name, email=email, reason=reason, message=message)
        return JsonResponse({"ok": True})

    return render(request, "pages/contact.html")
