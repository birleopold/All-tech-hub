from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from catalog.models import Category


CATEGORY_TREE = [
    (
        "Laptops",
        "Portable computers for business, education, gaming, creative work, and everyday use.",
        [
            "Business laptops",
            "Gaming laptops",
            "Student laptops",
            "MacBooks",
            "2-in-1 laptops",
            "Refurbished laptops",
        ],
    ),
    (
        "Desktop Computers",
        "Desktop systems for homes, offices, gaming, engineering, and professional workloads.",
        [
            "Complete desktop sets",
            "All-in-one computers",
            "Gaming desktops",
            "Mini PCs",
            "Workstations",
            "Refurbished desktops",
        ],
    ),
    (
        "Computer Components",
        "Internal computer parts used to build, upgrade, or repair desktop computers.",
        [
            "Processors",
            "Motherboards",
            "RAM",
            "Graphics cards",
            "Power supply units",
            "Computer cases",
            "Cooling fans and systems",
        ],
    ),
    (
        "Storage Devices",
        "Internal, external, and removable devices for storing and transferring data.",
        [
            "Internal hard drives",
            "External hard drives",
            "SATA SSDs",
            "M.2 and NVMe SSDs",
            "USB flash drives",
            "Memory cards",
            "Card readers",
        ],
    ),
    (
        "Monitors and Displays",
        "Computer displays, projectors, screens, and mounting accessories.",
        [
            "Computer monitors",
            "Gaming monitors",
            "Portable monitors",
            "Projectors",
            "Projector screens",
            "Monitor stands and mounts",
        ],
    ),
    (
        "Computer Accessories",
        "Keyboards, mice, laptop accessories, cables, adapters, hubs, and related peripherals.",
        [
            "Wired keyboards",
            "Wireless keyboards",
            "Gaming keyboards",
            "Wired mice",
            "Wireless mice",
            "Gaming mice",
            "Keyboard and mouse combos",
            "Mouse pads",
            "Laptop chargers",
            "Laptop batteries",
            "Laptop bags and backpacks",
            "Laptop stands",
            "Cooling pads",
            "Laptop covers and skins",
            "Laptop screen protectors",
            "Privacy filters",
            "HDMI cables",
            "DisplayPort cables",
            "VGA cables",
            "USB cables",
            "Type-C cables",
            "Ethernet cables",
            "OTG adapters",
            "USB hubs",
            "HDMI and VGA converters",
        ],
    ),
    (
        "Networking Equipment",
        "Devices and accessories for internet access, Wi-Fi coverage, and wired networks.",
        [
            "Wi-Fi routers",
            "MiFi devices",
            "Network switches",
            "Wi-Fi extenders",
            "Access points",
            "Network cables",
            "Modems",
            "Network adapters",
        ],
    ),
    (
        "Printers, Scanners and Supplies",
        "Printing, scanning, copying equipment and the consumables required to operate it.",
        [
            "Inkjet printers",
            "Laser printers",
            "All-in-one printers",
            "Receipt printers",
            "Barcode printers",
            "Scanners",
            "Photocopiers",
            "Ink cartridges",
            "Toner cartridges",
            "Refill ink",
            "Printer drums",
            "Thermal paper",
            "Printing paper",
            "Printer cables",
        ],
    ),
    (
        "Audio and Video",
        "Audio, video, conferencing, and communication accessories for computers and smart devices.",
        [
            "Headphones",
            "Earphones",
            "Computer speakers",
            "Bluetooth speakers",
            "Microphones",
            "Webcams",
            "Conference cameras",
            "Sound cards",
        ],
    ),
    (
        "Power and Electrical Accessories",
        "Power protection, backup power, charging, conversion, and electrical accessories.",
        [
            "UPS systems",
            "Surge protectors",
            "Extension cables",
            "Power banks",
            "Laptop power adapters",
            "Inverters",
            "Solar power accessories",
            "Voltage stabilizers",
        ],
    ),
    (
        "Gaming Equipment",
        "Gaming furniture, controls, headsets, and console accessories.",
        [
            "Gaming chairs",
            "Gaming headsets",
            "Game controllers",
            "PlayStation accessories",
            "Xbox accessories",
        ],
    ),
    (
        "Mobile, Tablets and Smart Devices",
        "Phones, tablets, wearables, smart entertainment devices, and mobile accessories.",
        [
            "Smartphones",
            "Tablets",
            "Feature phones",
            "Phone chargers",
            "Phone covers",
            "Mobile screen protectors",
            "Tablet keyboards",
            "Stylus pens",
            "Smart watches",
            "Fitness trackers",
            "Smart TVs",
            "TV boxes",
            "Smart home devices",
            "Bluetooth trackers",
            "Digital assistants",
        ],
    ),
    (
        "Security and Surveillance",
        "Video surveillance, access control, alarms, and security recording equipment.",
        [
            "CCTV cameras",
            "DVR and NVR systems",
            "Biometric machines",
            "Access-control systems",
            "Alarm systems",
            "Video doorbells",
            "Security storage drives",
        ],
    ),
    (
        "Software and Licences",
        "Operating systems, productivity software, security software, and specialist applications.",
        [
            "Windows licences",
            "Microsoft Office",
            "Antivirus software",
            "Accounting software",
            "Graphic-design software",
            "Educational software",
        ],
    ),
    (
        "Office Technology and Maintenance",
        "Office machines, point-of-sale equipment, maintenance tools, and replacement parts.",
        [
            "POS machines",
            "Barcode scanners",
            "Cash drawers",
            "Money-counting machines",
            "Laminating machines",
            "Binding machines",
            "Shredders",
            "Presentation clickers",
            "Computer cleaning kits",
            "Screwdriver sets",
            "Thermal paste",
            "Air blowers",
            "Cable organisers",
            "Laptop replacement parts",
            "Testing tools",
        ],
    ),
]


SHOPPING_SECTIONS = [
    "New Arrivals",
    "Best Sellers",
    "Special Offers",
    "Clearance Sale",
    "Refurbished Products",
    "Student Deals",
    "Business Solutions",
    "Gaming Zone",
    "Products by Brand",
    "Shop by Price",
]


class Command(BaseCommand):
    help = (
        "Create or update LEOSOFT's 15 main product categories and their "
        "subcategories without creating duplicates."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created or updated, then roll back all changes.",
        )
        parser.add_argument(
            "--main-only",
            action="store_true",
            help="Create only the 15 main menu categories and skip subcategories.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        main_only = options["main_only"]
        created_count = 0
        updated_count = 0
        unchanged_count = 0

        for main_index, (main_name, main_description, children) in enumerate(
            CATEGORY_TREE, start=1
        ):
            main_category, status = self._upsert_category(
                name=main_name,
                slug=slugify(main_name)[:140],
                description=main_description,
                sort_order=main_index * 100,
                parent=None,
            )
            created_count += status == "created"
            updated_count += status == "updated"
            unchanged_count += status == "unchanged"

            if main_only:
                continue

            for child_index, child_name in enumerate(children, start=1):
                child_slug = f"{main_category.slug}-{slugify(child_name)}"[:140]
                _, status = self._upsert_category(
                    name=child_name,
                    slug=child_slug,
                    description=f"{child_name} under {main_name}.",
                    sort_order=(main_index * 100) + child_index,
                    parent=main_category,
                )
                created_count += status == "created"
                updated_count += status == "updated"
                unchanged_count += status == "unchanged"

        if dry_run:
            transaction.set_rollback(True)

        action = "Dry run complete" if dry_run else "Category population complete"
        self.stdout.write(self.style.SUCCESS(action))
        self.stdout.write(f"Created: {created_count}")
        self.stdout.write(f"Updated: {updated_count}")
        self.stdout.write(f"Unchanged: {unchanged_count}")
        self.stdout.write(
            "Shopping sections were not inserted as categories because they should "
            "be generated from product flags, brands, prices, and promotions: "
            + ", ".join(SHOPPING_SECTIONS)
        )

    def _upsert_category(
        self,
        *,
        name: str,
        slug: str,
        description: str,
        sort_order: int,
        parent: Category | None,
    ) -> tuple[Category, str]:
        category, created = Category.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "description": description,
                "sort_order": sort_order,
                "parent": parent,
            },
        )
        if created:
            self.stdout.write(f"Created: {self._label(category)}")
            return category, "created"

        changed_fields = []
        desired_values = {
            "name": name,
            "description": description,
            "sort_order": sort_order,
            "parent": parent,
        }
        for field_name, desired_value in desired_values.items():
            current_value = getattr(category, field_name)
            if current_value != desired_value:
                setattr(category, field_name, desired_value)
                changed_fields.append(field_name)

        if changed_fields:
            category.save(update_fields=changed_fields)
            self.stdout.write(f"Updated: {self._label(category)}")
            return category, "updated"

        return category, "unchanged"

    @staticmethod
    def _label(category: Category) -> str:
        if category.parent_id:
            return f"{category.parent.name} > {category.name}"
        return category.name
