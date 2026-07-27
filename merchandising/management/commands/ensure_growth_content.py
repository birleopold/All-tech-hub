from __future__ import annotations

from django.core.management.base import BaseCommand

from merchandising.models import BuyingGuide, CommercialLandingFAQ, CommercialLandingPage


HUBS = (
    {
        "slug": "laptop-prices-in-uganda",
        "title": "Laptop Prices in Uganda",
        "label": "laptops",
        "category_keywords": "laptop,notebook",
        "search_terms": "laptop,notebook,portable computer",
        "guidance": "Compare the intended workload, processor generation, RAM, SSD capacity, screen, battery notes, condition and warranty. A lower price is useful only when the configuration and physical condition fit the work you need to do.",
    },
    {
        "slug": "dell-laptops-uganda",
        "title": "Dell Laptops in Uganda",
        "label": "Dell laptops",
        "brand": "Dell",
        "category_keywords": "laptop,notebook",
        "search_terms": "Dell Latitude,Dell Precision,Dell Inspiron,Dell XPS",
        "guidance": "Latitude models commonly suit business use, Precision models target heavier professional workloads, and Inspiron or XPS models vary widely by configuration. Confirm the exact model, processor generation and upgrade options rather than choosing by the Dell name alone.",
    },
    {
        "slug": "hp-laptops-uganda",
        "title": "HP Laptops in Uganda",
        "label": "HP laptops",
        "brand": "HP",
        "category_keywords": "laptop,notebook",
        "search_terms": "HP EliteBook,HP ProBook,HP ZBook,HP Pavilion,HP Spectre",
        "guidance": "EliteBook and ProBook systems are often selected for business, while ZBook models target workstation tasks. Check the exact processor, RAM, storage, graphics, display and condition because two visually similar HP models can perform very differently.",
    },
    {
        "slug": "lenovo-laptops-uganda",
        "title": "Lenovo Laptops in Uganda",
        "label": "Lenovo laptops",
        "brand": "Lenovo",
        "category_keywords": "laptop,notebook",
        "search_terms": "Lenovo ThinkPad,Lenovo ThinkBook,Lenovo Yoga,Lenovo IdeaPad",
        "guidance": "ThinkPad models are widely used for business durability, Yoga models focus on flexible or touch designs, and IdeaPad or ThinkBook configurations vary by market. Confirm the exact series, generation, keyboard, battery and upgrade support.",
    },
    {
        "slug": "macbook-prices-in-uganda",
        "title": "MacBook Prices in Uganda",
        "label": "MacBook computers",
        "brand": "Apple",
        "category_keywords": "laptop,notebook,macbook",
        "search_terms": "MacBook Air,MacBook Pro,Apple laptop,M1,M2,M3,M4",
        "guidance": "Check the exact Apple chip or Intel generation, RAM, storage, screen size, battery cycle or health note, charger, keyboard and macOS support. Apple memory and storage are generally not upgradeable after purchase, so select enough capacity from the beginning.",
    },
    {
        "slug": "refurbished-laptops-uganda",
        "title": "Refurbished Laptops in Uganda",
        "label": "refurbished laptops",
        "condition": "refurbished",
        "category_keywords": "laptop,notebook",
        "search_terms": "refurbished laptop,renewed laptop,ex UK laptop",
        "guidance": "A refurbished laptop should have a clear condition description, actual photos where possible, tested ports and keyboard, storage health, battery notes, included charger and written warranty. Compare the exact unit rather than relying only on the model name.",
    },
    {
        "slug": "business-laptops-uganda",
        "title": "Business Laptops in Uganda",
        "label": "business laptops",
        "category_keywords": "laptop,notebook",
        "search_terms": "business laptop,office laptop,Latitude,EliteBook,ProBook,ThinkPad,ThinkBook",
        "guidance": "Prioritise reliability, keyboard quality, battery, ports, security features, repairability and enough RAM for the applications used every day. Formal quotations and consistent configurations matter when buying several units for an organisation.",
    },
    {
        "slug": "student-laptops-uganda",
        "title": "Student Laptops in Uganda",
        "label": "student laptops",
        "category_keywords": "laptop,notebook",
        "search_terms": "student laptop,university laptop,school laptop,learning laptop",
        "guidance": "Match the laptop to the course rather than buying by price alone. General study may need modest specifications, while engineering, architecture, programming, media and design courses can require more RAM, storage, graphics and screen quality.",
    },
    {
        "slug": "gaming-laptops-uganda",
        "title": "Gaming Laptops in Uganda",
        "label": "gaming laptops",
        "category_keywords": "laptop,notebook,gaming",
        "search_terms": "gaming laptop,GeForce,RTX,GTX,Radeon gaming",
        "guidance": "Confirm the dedicated graphics model and power level, processor, RAM, cooling, screen refresh rate, storage and charger. A laptop described as gaming without clear graphics information should be reviewed carefully before purchase.",
    },
    {
        "slug": "workstation-laptops-uganda",
        "title": "Mobile Workstation Laptops in Uganda",
        "label": "workstation laptops",
        "category_keywords": "laptop,workstation",
        "search_terms": "mobile workstation,Dell Precision,HP ZBook,ThinkPad P,Quadro,RTX workstation",
        "guidance": "Workstation laptops are built for demanding professional tasks, but performance depends on the exact CPU, professional graphics, RAM, storage, cooling and software requirements. Confirm application compatibility before selecting a unit.",
    },
    {
        "slug": "core-i5-laptops-uganda",
        "title": "Core i5 Laptops in Uganda",
        "label": "Core i5 laptops",
        "category_keywords": "laptop,notebook",
        "search_terms": "Core i5,i5 laptop,Intel i5",
        "guidance": "Core i5 is a product family, not one fixed performance level. Compare the processor generation and exact model together with RAM, SSD, cooling and workload. A newer efficient i5 can outperform an older processor with a higher-looking label.",
    },
    {
        "slug": "core-i7-laptops-uganda",
        "title": "Core i7 Laptops in Uganda",
        "label": "Core i7 laptops",
        "category_keywords": "laptop,notebook",
        "search_terms": "Core i7,i7 laptop,Intel i7",
        "guidance": "Do not judge an i7 laptop by the family name alone. Check generation, core class, power limit, RAM, storage, graphics and cooling. An older i7 may be less suitable than a newer mid-range processor for some workloads.",
    },
    {
        "slug": "touchscreen-laptops-uganda",
        "title": "Touchscreen Laptops in Uganda",
        "label": "touchscreen laptops",
        "category_keywords": "laptop,notebook",
        "search_terms": "touchscreen laptop,2 in 1 laptop,convertible laptop,x360,Yoga",
        "guidance": "Confirm whether the display is touch-only or a full convertible design, and check hinge condition, pen support, resolution, brightness and replacement cost. Touch capability should support a real use case rather than simply increasing the purchase price.",
    },
    {
        "slug": "desktop-computer-prices-in-uganda",
        "title": "Desktop Computer Prices in Uganda",
        "label": "desktop computers",
        "category_keywords": "desktop,computer,workstation,tower,all in one",
        "search_terms": "desktop computer,office desktop,tower PC,all in one computer",
        "guidance": "Check processor generation, RAM, SSD or hard drive, graphics, expansion options, power supply, included monitor and operating system. Business desktops can provide excellent value when portability is not required.",
    },
    {
        "slug": "printer-prices-in-uganda",
        "title": "Printer Prices in Uganda",
        "label": "printers",
        "category_keywords": "printer,printing,scanner,copier",
        "search_terms": "laser printer,ink printer,multifunction printer,scanner,photocopier",
        "guidance": "Compare print volume, colour requirement, duplex printing, scanning, network support, cartridge or toner availability and cost per page. The cheapest printer can become expensive when consumables are difficult to find.",
    },
    {
        "slug": "wifi-router-prices-in-uganda",
        "title": "Wi-Fi Router Prices in Uganda",
        "label": "Wi-Fi routers",
        "category_keywords": "router,networking,wifi,internet",
        "search_terms": "Wi-Fi router,wireless router,4G router,5G router,mesh Wi-Fi,access point",
        "guidance": "Match the router to the internet source, coverage area, number of users, building layout, required Wi-Fi standard and network-management features. Large homes and offices may need multiple access points or a mesh system rather than one powerful-looking router.",
    },
    {
        "slug": "cctv-camera-prices-in-uganda",
        "title": "CCTV Camera Prices in Uganda",
        "label": "CCTV and surveillance equipment",
        "category_keywords": "cctv,camera,surveillance,security,dvr,nvr",
        "search_terms": "CCTV camera,security camera,DVR,NVR,IP camera,analogue camera",
        "guidance": "A complete CCTV decision includes camera type and resolution, night performance, recorder channels, storage duration, cable or network design, power backup, installation location and remote viewing. Request a site-informed quotation for a complete system.",
    },
    {
        "slug": "ssd-prices-in-uganda",
        "title": "SSD Prices in Uganda",
        "label": "solid-state drives",
        "category_keywords": "ssd,storage,drive,computer accessories",
        "search_terms": "SSD,SATA SSD,NVMe SSD,M.2 SSD,solid state drive",
        "guidance": "Confirm the physical format, interface, capacity, motherboard compatibility and intended workload. A SATA 2.5-inch drive, M.2 SATA drive and M.2 NVMe drive can look similar in a listing but are not interchangeable in every computer.",
    },
    {
        "slug": "external-hard-drive-prices-in-uganda",
        "title": "External Hard Drive Prices in Uganda",
        "label": "external storage drives",
        "category_keywords": "hard drive,storage,external drive,backup",
        "search_terms": "external hard drive,portable hard disk,external SSD,backup drive",
        "guidance": "Choose capacity, drive type, connection speed, physical protection and backup purpose. One external drive is not a complete backup strategy for irreplaceable information; important files should have another independent copy.",
    },
    {
        "slug": "computer-accessories-uganda",
        "title": "Computer Accessories in Uganda",
        "label": "computer accessories",
        "category_keywords": "accessory,computer accessories,charger,keyboard,mouse,dock,cable",
        "search_terms": "laptop charger,keyboard,mouse,docking station,adapter,cable,computer accessory",
        "guidance": "Compatibility matters more than appearance. Confirm connector type, voltage and wattage, operating-system support, device model and required function before buying chargers, docks, adapters, memory, storage or display accessories.",
    },
    {
        "slug": "monitor-prices-in-uganda",
        "title": "Computer Monitor Prices in Uganda",
        "label": "computer monitors",
        "category_keywords": "monitor,display,screen,computer accessories",
        "search_terms": "computer monitor,LED monitor,gaming monitor,office monitor,display",
        "guidance": "Compare size, resolution, panel type, refresh rate, ports, stand adjustment and the computer's output support. A larger screen with low resolution may provide less useful workspace than a smaller sharper display.",
    },
    {
        "slug": "ups-prices-in-uganda",
        "title": "UPS Prices in Uganda",
        "label": "UPS and power backup equipment",
        "category_keywords": "ups,power backup,inverter,power protection",
        "search_terms": "UPS,uninterruptible power supply,power backup,computer UPS",
        "guidance": "Select a UPS by the real equipment load, required runtime, battery condition, output type and replacement-battery availability. A UPS protects against short interruptions and unsafe shutdowns; it should not be sized only by the number printed on its case.",
    },
)


GUIDES = (
    {
        "slug": "how-to-choose-a-laptop-in-uganda",
        "title": "How to Choose a Laptop in Uganda",
        "excerpt": "A practical process for matching processor, memory, storage, screen, condition and support to the work you need to do.",
        "keywords": "laptop,notebook,student laptop,business laptop",
        "categories": "laptop,notebook",
        "body": """Start with the work, not the brand badge. List the applications, number of browser tabs, files, meetings, design tools or technical programs the computer must handle. This determines the processor class, RAM, storage and graphics that matter.

Check the complete configuration. Processor generation, RAM capacity, SSD type, screen, ports, battery notes, keyboard, charger and condition all affect daily use. A strong processor cannot compensate for insufficient memory, failing storage or poor physical condition.

For refurbished and used systems, review actual photographs and written condition notes. Confirm stock, warranty, included items, delivery and the final price before paying. Keep the quotation, invoice, receipt and warranty information for future support.""",
    },
    {
        "slug": "how-to-inspect-a-refurbished-laptop",
        "title": "How to Inspect a Refurbished Laptop Before Buying",
        "excerpt": "A transparent checklist for condition, battery, display, keyboard, ports, storage, charger, warranty and actual photographs.",
        "keywords": "refurbished laptop,used laptop,condition,battery",
        "categories": "laptop,notebook",
        "body": """Begin by confirming the exact model and configuration. Check the processor, RAM, storage, screen type and graphics against the written listing. Similar-looking models can have very different internal specifications.

Inspect the display, hinges, keyboard, touchpad, casing, ports, webcam, speakers, Wi-Fi and charger. Ask for battery-health or runtime information where available and confirm whether photographs show the actual unit or representative stock.

Request written condition notes, warranty terms and included accessories. Test the unit before travelling away where possible, and keep formal sales documents so any support request can be traced to the exact product supplied.""",
    },
    {
        "slug": "dell-latitude-vs-hp-elitebook-vs-lenovo-thinkpad",
        "title": "Dell Latitude vs HP EliteBook vs Lenovo ThinkPad",
        "excerpt": "How to compare three major business-laptop families by generation, construction, ports, keyboard, repairability and actual configuration.",
        "keywords": "Dell Latitude,HP EliteBook,Lenovo ThinkPad,business laptop",
        "categories": "laptop,notebook",
        "body": """Latitude, EliteBook and ThinkPad are broad business families, not single specifications. Each includes multiple sizes, generations and performance levels. Compare the exact model rather than assuming one brand is always stronger.

Review processor generation, RAM and storage upgrade options, screen, keyboard, ports, battery, weight and physical condition. Workstation versions may include stronger graphics but also use more power and larger chargers.

The best choice is the unit whose verified configuration, condition, warranty and price fit the workload. A well-documented mid-range model can be a better purchase than a poorly described premium label.""",
    },
    {
        "slug": "8gb-vs-16gb-ram-laptop-guide",
        "title": "8GB vs 16GB RAM: Which Laptop Memory Is Enough?",
        "excerpt": "A workload-based guide to choosing memory for study, office work, programming, design, engineering and multitasking.",
        "keywords": "8GB RAM,16GB RAM,laptop memory,computer RAM",
        "categories": "laptop,desktop,memory",
        "body": """Eight gigabytes can handle basic office work, web browsing, online learning and light multitasking when the operating system and applications are well managed. Heavy browser use and multiple large applications can quickly consume it.

Sixteen gigabytes provides more room for programming tools, large spreadsheets, design applications, virtual meetings and longer useful life. Engineering, video, advanced design, virtual machines and large datasets may require more.

Also confirm whether the computer's memory is upgradeable, how many slots it has and whether part of the memory is soldered. Buying an upgradeable model can be more economical than replacing the whole computer later.""",
    },
    {
        "slug": "ssd-vs-hdd-storage-guide",
        "title": "SSD vs HDD: Choosing Computer Storage",
        "excerpt": "Understand speed, capacity, reliability, compatibility and backup considerations before choosing storage.",
        "keywords": "SSD,HDD,NVMe,SATA,computer storage",
        "categories": "storage,ssd,hard drive,laptop,desktop",
        "body": """An SSD usually makes a computer start, open applications and access files much faster than a mechanical hard drive. NVMe SSDs can be faster than SATA SSDs, but the computer must support the correct interface.

Hard drives remain useful when large capacity is needed at a lower price, especially for archives and backup copies. Mechanical parts make them more sensitive to impact and slower for active operating-system use.

Confirm format, interface and capacity before purchase. Keep important information in more than one place; changing to an SSD improves speed but does not replace a proper backup plan.""",
    },
    {
        "slug": "computer-procurement-guide-schools-ngos",
        "title": "Computer Procurement Guide for Schools, NGOs and Businesses",
        "excerpt": "A structured approach to specifications, consistency, documentation, deployment, warranty and support for multi-unit purchases.",
        "keywords": "computer procurement,school computers,NGO laptops,business computers,quotation",
        "categories": "laptop,desktop,printer,networking",
        "body": """Begin with users, applications and deployment conditions. Define minimum specifications, operating system, ports, accessories, power protection, connectivity and support rather than requesting only a brand or processor family.

For several units, consistency simplifies software deployment, spares, training and maintenance. Confirm exact configurations, condition, stock availability, serial tracking, warranty and delivery schedule in writing.

Use a formal quotation and retain approvals, invoices, receipts and warranty records. Include setup, data migration, networking, security, user orientation and maintenance where the organisation needs a complete operational result rather than boxes of equipment.""",
    },
    {
        "slug": "wifi-router-buying-guide-uganda",
        "title": "Wi-Fi Router Buying Guide for Uganda",
        "excerpt": "Choose a router using internet source, coverage, users, building layout, Wi-Fi standard and network-management requirements.",
        "keywords": "Wi-Fi router,4G router,5G router,mesh Wi-Fi,access point",
        "categories": "router,networking,wifi,internet",
        "body": """First identify the internet source: fibre or Ethernet, mobile SIM, radio link or another upstream router. The WAN connection determines which router types are compatible.

Estimate coverage and simultaneous users. Walls, floors, interference and long distances reduce signal quality. A large building may require wired access points or mesh nodes rather than one central router.

Check Wi-Fi standard, Ethernet-port speed, SIM bands where relevant, management controls, guest networks, power requirements and installation support. Position and configuration can affect performance as much as the device specification.""",
    },
    {
        "slug": "laptop-battery-health-guide",
        "title": "Laptop Battery Health and Buying Guide",
        "excerpt": "Understand battery condition, cycle information, runtime expectations and why an exact written promise matters for used devices.",
        "keywords": "laptop battery,battery health,battery cycles,refurbished laptop",
        "categories": "laptop,notebook,battery",
        "body": """Battery runtime depends on age, capacity, workload, screen brightness, power settings and the exact battery fitted. A percentage reading at one moment is not a complete health assessment.

For a used or refurbished laptop, ask for available battery-health, cycle or practical runtime information and understand whether the battery is covered by the same warranty as the rest of the unit. Replacement availability and cost also matter.

Treat unusually precise runtime claims carefully unless they describe the test conditions. Keep the charger specification and avoid unsafe incompatible adapters that can damage performance or charging reliability.""",
    },
)


class Command(BaseCommand):
    help = "Create missing commercial hubs, FAQs and foundational buying guides without overwriting staff edits."

    def handle(self, *args, **options):
        hub_created = 0
        faq_created = 0
        guide_created = 0

        for order, definition in enumerate(HUBS, start=1):
            label = definition["label"]
            page, created = CommercialLandingPage.objects.get_or_create(
                slug=definition["slug"],
                defaults={
                    "title": definition["title"],
                    "eyebrow": "Current technology catalogue and buying guidance",
                    "meta_description": (
                        f"Compare current {label} in Uganda with prices, condition, "
                        "availability, specifications, formal quotations and LEOSOFT support."
                    )[:320],
                    "intro": (
                        f"Browse current {label} from the live LEOSOFT catalogue. "
                        "Compare verified specifications, condition, price and availability, "
                        "then request guidance or a formal quotation before paying."
                    ),
                    "buying_guidance": definition["guidance"],
                    "category_keywords": definition.get("category_keywords", ""),
                    "brand": definition.get("brand", ""),
                    "condition": definition.get("condition", ""),
                    "search_terms": definition.get("search_terms", ""),
                    "sort_order": order,
                    "is_published": True,
                },
            )
            hub_created += int(created)
            faq_defaults = (
                (
                    f"How much do {label} cost in Uganda?",
                    "Prices depend on the exact model, configuration, condition and current stock. The live products above show current recorded prices; confirm the selected option and delivery before payment.",
                ),
                (
                    f"Can I request a formal quotation for {label}?",
                    "Yes. LEOSOFT can prepare a formal quotation for personal, school, NGO or business procurement after the required configuration and quantity are confirmed.",
                ),
                (
                    f"How do I confirm the condition and availability of {label}?",
                    "Review the product page and actual photographs where provided, then contact the team to confirm the exact unit, stock, warranty, included items and delivery or collection arrangements.",
                ),
            )
            for position, (question, answer) in enumerate(faq_defaults, start=1):
                _, faq_was_created = CommercialLandingFAQ.objects.get_or_create(
                    page=page,
                    question=question,
                    defaults={"answer": answer, "sort_order": position},
                )
                faq_created += int(faq_was_created)

        for definition in GUIDES:
            _, created = BuyingGuide.objects.get_or_create(
                slug=definition["slug"],
                defaults={
                    "title": definition["title"],
                    "excerpt": definition["excerpt"],
                    "body": definition["body"],
                    "author_name": "LEOSOFT Technical Team",
                    "reviewer_name": "LEOSOFT Catalogue Review",
                    "keywords": definition["keywords"],
                    "related_category_keywords": definition["categories"],
                    "is_published": True,
                },
            )
            guide_created += int(created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Growth content ready: {hub_created} hubs, {faq_created} FAQs and "
                f"{guide_created} buying guides created; existing staff content preserved."
            )
        )
