"""Create standard ALLTECH staff roles and optionally assign a user."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError

ROLE_PERMISSIONS = {
    "Technician": {
        "operations": {"jobcard", "jobnote", "timeentry", "jobattachment"},
        "core": {"supportticket", "ticketcomment", "staffnotification"},
        "inventory": {"stockadjustment", "stockmovement"},
    },
    "Sales": {
        "commerce": {
            "order", "orderline", "coupon", "customerreturn",
            "orderstatusevent", "orderstockrestoration", "shipment",
        },
        "billing": {
            "commercialdocument", "commercialline", "documenttemplate",
        },
        "crm": {"customer", "customeraddress"},
        "catalog": {"product", "productvariant", "productreview"},
        "core": {"contactmessage", "supportticket"},
        "messaging": {"outboundemail"},
    },
    "Inventory": {
        "catalog": {"category", "product", "productvariant", "productserial"},
        "inventory": {
            "stockadjustment", "stockmovement", "stocktake", "stocktakeline"
        },
        "purchasing": {
            "supplier", "purchaseorder", "purchaseline", "stockreceipt",
            "stockreceiptline", "supplierreturn",
        },
        "operations": {"jobcard"},
    },
    "Finance": {
        "billing": {
            "commercialdocument", "commercialline", "documentpayment",
            "documentsequence", "paymentrefund", "documentrevision",
            "documenttemplate", "customercredit", "accountpayment",
            "paymentallocation",
        },
        "commerce": {"order", "orderline", "coupon"},
        "crm": {"customer"},
        "messaging": {"outboundemail"},
        "core": {"auditevent"},
    },
}


class Command(BaseCommand):
    help = "Create/update Technician, Sales, Inventory, Finance and Manager groups."

    def add_arguments(self, parser):
        parser.add_argument("--assign", help="Username to add to a role.")
        parser.add_argument(
            "--role",
            choices=[*ROLE_PERMISSIONS, "Manager"],
            help="Role used with --assign.",
        )

    def handle(self, *args, **options):
        project_apps = set(ROLE_PERMISSIONS["Technician"]) | set(
            ROLE_PERMISSIONS["Sales"]
        ) | set(ROLE_PERMISSIONS["Inventory"]) | set(ROLE_PERMISSIONS["Finance"])
        project_apps |= {"portal", "reports", "dashboard"}

        for role, app_models in ROLE_PERMISSIONS.items():
            group, _ = Group.objects.get_or_create(name=role)
            permissions = Permission.objects.none()
            for app_label, models in app_models.items():
                permissions = permissions | Permission.objects.filter(
                    content_type__app_label=app_label,
                    content_type__model__in=models,
                )
            group.permissions.set(permissions.distinct())
            self.stdout.write(self.style.SUCCESS(f"Updated role: {role}"))

        manager, _ = Group.objects.get_or_create(name="Manager")
        manager.permissions.set(
            Permission.objects.filter(content_type__app_label__in=project_apps)
        )
        self.stdout.write(self.style.SUCCESS("Updated role: Manager"))

        if options["assign"]:
            if not options["role"]:
                raise CommandError("--role is required when using --assign.")
            User = get_user_model()
            try:
                user = User.objects.get(username=options["assign"])
            except User.DoesNotExist as exc:
                raise CommandError("User does not exist.") from exc
            user.is_staff = True
            user.save(update_fields=["is_staff"])
            user.groups.add(Group.objects.get(name=options["role"]))
            self.stdout.write(
                self.style.SUCCESS(
                    f"Assigned {user.get_username()} to {options['role']}."
                )
            )
