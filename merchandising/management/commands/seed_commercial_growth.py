from __future__ import annotations

from django.core.management.base import BaseCommand

from merchandising.models import (
    BuyingGuide,
    CommercialLandingFAQ,
    CommercialLandingPage,
    DeliveryZone,
)


PAGES = [
    {
        "slug": "laptop-prices-in-uganda",
        "title": "Laptop Prices in Uganda",
        "eyebrow": "Live laptop catalogue and buying guidance",
        "meta_description": "Compare current laptop prices in Uganda, condition, specifications, stock and warranty guidance from LEOSOFT, then request a formal quotation.",
        "intro": "Compare laptops using live catalogue prices instead of a generic price list. Each available option can be checked by brand, processor, RAM, storage, condition and intended use, with support before and after purchase.",
        "buying_guidance": "Start with the work the laptop must perform. Office, school and browsing needs are different from engineering, video editing and gaming. Compare the processor generation, RAM capacity, SSD size, screen, battery note, condition and included charger. A cheaper machine can become expensive when it needs an immediate battery, storage or memory replacement. Confirm the exact configuration and current stock before paying.",
        "category_keywords": "laptop,notebook,macbook",
        "search_terms": "latitude,elitebook,probook,thinkpad,thinkbook,ideapad,zbook,precision,macbook",
        "sort_order": 1,
        "faqs": [
            ("What affects laptop prices in Uganda?", "Brand, processor generation, RAM, SSD capacity, screen features, graphics, battery condition, physical condition, warranty and whether the device is new, refurbished or used all affect price."),
            ("Are the prices on this page current?", "The page draws from the live LEOSOFT catalogue. Stock and final delivery charges should still be confirmed before payment because technology inventory changes quickly."),
            ("Can LEOSOFT prepare a formal quotation?", "Yes. Schools, NGOs, companies and individual buyers can request a quotation showing the selected model, configuration, price and applicable services."),
        ],
    },
    {
        "slug": "dell-laptops-uganda",
        "title": "Dell Laptops in Uganda",
        "eyebrow": "Dell Latitude, Precision, Inspiron and business options",
        "meta_description": "Browse Dell laptop prices in Uganda, including Latitude, Precision and other available models with clear condition, specifications and quotation support.",
        "intro": "Explore Dell laptops available through LEOSOFT and compare the exact model, processor, RAM, storage, screen, condition and stock. Business buyers can also request documented configurations and formal quotations.",
        "buying_guidance": "Latitude models are commonly selected for business portability and serviceability, while Precision systems target heavier professional workloads. Inspiron and other consumer lines vary widely, so compare the exact series rather than relying on the Dell name alone. Confirm the generation, screen size, keyboard, ports, battery note and charger.",
        "category_keywords": "laptop,notebook",
        "brand": "Dell",
        "search_terms": "latitude,precision,inspiron,vostro,xps",
        "sort_order": 2,
        "faqs": [
            ("Which Dell laptop is suitable for business?", "Latitude models are often practical for office work, travel and managed business environments. The correct model still depends on processor, RAM, storage, screen and required ports."),
            ("What is the difference between Dell Latitude and Precision?", "Latitude focuses mainly on professional mobility and office use. Precision models are mobile workstations designed for demanding engineering, design and technical software."),
        ],
    },
    {
        "slug": "hp-laptops-uganda",
        "title": "HP Laptops in Uganda",
        "eyebrow": "HP EliteBook, ProBook, ZBook and everyday laptops",
        "meta_description": "Compare HP laptop prices in Uganda, specifications, condition and stock for EliteBook, ProBook, ZBook and other available HP models.",
        "intro": "Browse current HP laptops from the live catalogue and compare professional, student and performance configurations. Product pages can show inspected specifications, condition notes, included accessories and warranty information.",
        "buying_guidance": "EliteBook systems are normally positioned as premium business laptops, ProBook systems as practical business options, and ZBook systems as professional workstations. Generation names alone are not enough: compare the exact processor, RAM, SSD, graphics, display and battery note before choosing.",
        "category_keywords": "laptop,notebook",
        "brand": "HP",
        "search_terms": "elitebook,probook,zbook,pavilion,envy,omen,spectre",
        "sort_order": 3,
        "faqs": [
            ("Is an HP EliteBook good for students?", "An EliteBook can be a strong student option when the configuration, battery condition and price suit the course. It is especially useful for students who value durability and a professional keyboard."),
            ("When should I choose an HP ZBook?", "Choose a ZBook when the work genuinely needs workstation-class processors or graphics, such as engineering, architecture, 3D work or demanding creative software."),
        ],
    },
    {
        "slug": "lenovo-laptops-uganda",
        "title": "Lenovo Laptops in Uganda",
        "eyebrow": "ThinkPad, ThinkBook, IdeaPad and performance options",
        "meta_description": "Browse Lenovo laptop prices in Uganda and compare ThinkPad, ThinkBook, IdeaPad and other available models by condition and specification.",
        "intro": "Compare available Lenovo laptops using live prices and clear catalogue data. LEOSOFT can help identify the right ThinkPad, ThinkBook, IdeaPad or performance model for the intended work.",
        "buying_guidance": "ThinkPad models are well known for business keyboards, repairability and professional use, but different T, X, L, P and E series serve different needs. ThinkBook blends business styling with mainstream features, while IdeaPad commonly targets home and student users. Check the exact series, generation and configuration.",
        "category_keywords": "laptop,notebook",
        "brand": "Lenovo",
        "search_terms": "thinkpad,thinkbook,ideapad,legion,yoga,loq",
        "sort_order": 4,
        "faqs": [
            ("Why do many professionals choose ThinkPad laptops?", "ThinkPads are often chosen for their keyboards, business design, durability and serviceability. The actual value depends on the model series and condition."),
            ("Is ThinkBook the same as ThinkPad?", "No. ThinkBook generally combines business appearance with mainstream features, while ThinkPad is Lenovo's established professional line with several business-focused series."),
        ],
    },
    {
        "slug": "macbook-prices-in-uganda",
        "title": "MacBook Prices in Uganda",
        "eyebrow": "Apple MacBook Air and MacBook Pro buying hub",
        "meta_description": "Compare current MacBook prices in Uganda, chip or processor, memory, storage, battery notes, condition and included charger from LEOSOFT.",
        "intro": "Compare MacBook Air and MacBook Pro options by year, processor or Apple silicon chip, memory, storage, screen size, battery note and condition. Confirm software compatibility before moving from Windows.",
        "buying_guidance": "Choose the operating system first, not only the appearance. Confirm whether required accounting, engineering or institutional software runs properly on macOS. Apple silicon models and older Intel models differ greatly in performance, heat, battery life and software support. Check activation status, battery condition, keyboard, display, ports and charger before purchase.",
        "category_keywords": "laptop,notebook,macbook",
        "brand": "Apple",
        "search_terms": "macbook,macbook air,macbook pro,m1,m2,m3,m4,intel mac",
        "sort_order": 5,
        "faqs": [
            ("Should I buy a MacBook Air or MacBook Pro?", "MacBook Air suits portability and general work, while MacBook Pro models target sustained professional workloads. Compare the exact chip, memory, cooling, ports and display rather than the name alone."),
            ("Can a MacBook run Windows programs?", "Some Windows applications have macOS versions or browser alternatives, while others do not. Compatibility should be checked for the exact software and Mac model before purchase."),
        ],
    },
    {
        "slug": "refurbished-laptops-uganda",
        "title": "Refurbished Laptops in Uganda",
        "eyebrow": "Clearly identified pre-owned technology",
        "meta_description": "Browse refurbished laptop prices in Uganda with clear condition notes, actual-photo confirmation, tested specifications and warranty guidance.",
        "intro": "A refurbished laptop should be sold with clear condition information, not presented as new. Compare tested specifications, physical condition, battery note, keyboard, charger, warranty and actual images before deciding.",
        "buying_guidance": "Inspect the display, keyboard, hinges, ports, webcam, speakers, Wi-Fi, storage health, memory, battery and charger. Confirm that the serial, model and installed specifications match the quotation. Refurbished can offer strong value when the condition is documented and the model still supports the required software.",
        "category_keywords": "laptop,notebook,macbook",
        "condition": "refurbished",
        "search_terms": "latitude,elitebook,probook,thinkpad,macbook,precision,zbook",
        "sort_order": 6,
        "faqs": [
            ("What does refurbished mean?", "Refurbished describes previously owned equipment prepared for resale. It should be clearly labelled and accompanied by honest information about testing, physical condition and warranty."),
            ("How can I reduce risk when buying a refurbished laptop?", "Use actual photos, verify the exact specifications, test major components, confirm battery and charger information, request a receipt and understand the warranty terms."),
        ],
    },
    {
        "slug": "business-laptops-uganda",
        "title": "Business Laptops in Uganda",
        "eyebrow": "Professional computers and procurement support",
        "meta_description": "Compare business laptops in Uganda for office teams, remote work and organisational procurement, with quotations, warranty and after-sales support.",
        "intro": "Find professional laptops for individual work, teams and organisational procurement. Compare durability, keyboard, security, ports, docking, upgrade options, warranty and total cost rather than price alone.",
        "buying_guidance": "For office work, prioritise a dependable processor, at least practical working memory, SSD storage, a comfortable keyboard and suitable ports. Organisations should standardise models where possible, document serial numbers and warranty, and consider setup, data transfer, antivirus policy and maintenance support.",
        "category_keywords": "laptop,notebook",
        "search_terms": "business,latitude,elitebook,probook,thinkpad,thinkbook,precision,zbook",
        "sort_order": 7,
        "faqs": [
            ("What makes a laptop suitable for business?", "A suitable business laptop combines dependable performance, build quality, security, ports, manageable warranty and support. Standardisation can also reduce maintenance costs for teams."),
            ("Can LEOSOFT quote several laptops for an organisation?", "Yes. A formal quotation can document quantities, configurations, unit prices and related setup or support services."),
        ],
    },
    {
        "slug": "student-laptops-uganda",
        "title": "Student Laptops in Uganda",
        "eyebrow": "Laptops for university, secondary school and research",
        "meta_description": "Compare student laptop prices in Uganda by course, budget, battery needs, RAM, SSD and portability, with practical guidance from LEOSOFT.",
        "intro": "Choose a student laptop according to the course, software and daily movement. Compare weight, battery note, keyboard, RAM, SSD, webcam, screen and durability instead of buying by processor label alone.",
        "buying_guidance": "A student doing writing, research and online classes has different needs from one studying engineering, architecture, statistics or media. Confirm the required applications with the department. Prioritise an SSD, enough RAM for the workload, dependable Wi-Fi and a charger that is easy to replace. Keep part of the budget for a sleeve, backup and maintenance.",
        "category_keywords": "laptop,notebook,macbook",
        "search_terms": "student,school,university,coursework,research,portable",
        "sort_order": 8,
        "faqs": [
            ("Is 8GB RAM enough for a student?", "It is often enough for documents, browsing and online classes, but 16GB is safer for heavier multitasking, engineering, statistics, design and long-term use."),
            ("How much storage should a student laptop have?", "A 256GB SSD can work for documents and cloud use, while 512GB provides more room for applications, project files and offline content."),
        ],
    },
    {
        "slug": "gaming-laptops-uganda",
        "title": "Gaming Laptops in Uganda",
        "eyebrow": "Performance laptops for gaming and demanding software",
        "meta_description": "Compare gaming laptop prices in Uganda by graphics, processor, RAM, cooling, display and storage, with condition and warranty information.",
        "intro": "Gaming and performance laptops should be compared by graphics processor, power limits, cooling, screen refresh rate, RAM, SSD and charger—not by the word gaming alone.",
        "buying_guidance": "Check the exact graphics model and memory, processor generation, cooling condition and charger wattage. A thin laptop with the same graphics name may perform differently from a larger model. For used or refurbished systems, test temperatures, fans, battery, display and charging under load.",
        "category_keywords": "laptop,notebook",
        "search_terms": "gaming,rtx,gtx,omen,legion,loq,predator,rog,tuf,graphics",
        "sort_order": 9,
        "faqs": [
            ("What is most important in a gaming laptop?", "The graphics processor, cooling, processor, RAM, SSD, display and power system work together. The exact graphics model and its configured power matter greatly."),
            ("Can a gaming laptop be used for engineering or design?", "Often yes, especially where software benefits from dedicated graphics. Confirm the software requirements, graphics compatibility, RAM and display needs."),
        ],
    },
    {
        "slug": "desktop-computer-prices-in-uganda",
        "title": "Desktop Computer Prices in Uganda",
        "eyebrow": "Office desktops, workstations and complete systems",
        "meta_description": "Compare desktop computer prices in Uganda for offices, schools, workstations and home use, including processor, RAM, storage and support.",
        "intro": "Browse desktop computers and workstations for offices, schools, home and technical workloads. Confirm whether the price includes a monitor, keyboard, mouse, Wi-Fi and operating system.",
        "buying_guidance": "A desktop can offer easier upgrades and better sustained performance than a similarly priced laptop. Compare the case size, power supply, processor, RAM slots, storage, graphics and monitor connections. For complete installations, include the monitor, power protection, networking and setup in the budget.",
        "category_keywords": "desktop,computer,workstation,tower,all in one",
        "search_terms": "optiplex,prodesk,elitedesk,thinkcentre,precision,workstation,all-in-one",
        "sort_order": 10,
        "faqs": [
            ("Does a desktop price include a monitor?", "Not always. Confirm whether the listing is for the system unit only or a complete set with monitor, keyboard, mouse and cables."),
            ("Is a desktop better than a laptop?", "A desktop is often easier to upgrade and can offer stronger sustained performance, while a laptop provides portability and an integrated battery and screen."),
        ],
    },
    {
        "slug": "printer-prices-in-uganda",
        "title": "Printer Prices in Uganda",
        "eyebrow": "Home, office and institutional printing",
        "meta_description": "Compare printer prices in Uganda by ink or toner cost, print volume, colour, duplex, networking and maintenance support.",
        "intro": "Choose a printer using monthly print volume and running cost, not purchase price alone. Compare ink or toner availability, page yield, colour needs, duplex printing, scanning, networking and service support.",
        "buying_guidance": "Estimate how many pages will be printed each month and whether colour is essential. A low purchase price can lead to high ink costs. Confirm cartridge or bottle availability, duty cycle, automatic duplex, paper sizes, Wi-Fi or Ethernet and whether scanning and copying are required.",
        "category_keywords": "printer,printing,scanner,copier",
        "search_terms": "laserjet,deskjet,ink tank,ecotank,multifunction,toner,inkjet",
        "sort_order": 11,
        "faqs": [
            ("Should I choose an inkjet or laser printer?", "Inkjet systems can suit colour and lower-volume use, while laser printers are often practical for consistent office document printing. Compare the total running cost and available consumables."),
            ("What is a multifunction printer?", "A multifunction printer combines printing with functions such as scanning and copying, and sometimes faxing."),
        ],
    },
    {
        "slug": "wifi-router-prices-in-uganda",
        "title": "Wi-Fi Router Prices in Uganda",
        "eyebrow": "Routers, access points and internet coverage",
        "meta_description": "Compare Wi-Fi router prices in Uganda by coverage, speed, users, ports, mobile network support and installation guidance.",
        "intro": "Choose a router according to the internet source, building size, wall layout, number of users and devices. Coverage claims alone do not guarantee reliable performance in a real building.",
        "buying_guidance": "First identify whether the connection is fibre, Ethernet, DSL or mobile 4G/5G. Count active users and high-bandwidth devices. Check Wi-Fi standard, frequency bands, Ethernet ports, SIM compatibility, antenna design and management features. Larger offices or homes may need multiple access points or a mesh system rather than one powerful router.",
        "category_keywords": "router,networking,access point,wifi,modem",
        "search_terms": "4g,5g,dual band,mesh,ethernet,wireless,access point",
        "sort_order": 12,
        "faqs": [
            ("Why does one router not cover the whole building?", "Walls, floors, interference, placement and building shape weaken Wi-Fi. A planned access-point or mesh setup may provide better coverage than one router."),
            ("Can every router use a SIM card?", "No. Only routers designed with compatible cellular modems and SIM support can connect directly to a mobile network."),
        ],
    },
]


GUIDES = [
    {
        "slug": "best-laptops-for-university-students-in-uganda",
        "title": "Best Laptops for University Students in Uganda",
        "excerpt": "Choose a student laptop by course requirements, portability, battery, memory, storage and realistic total cost.",
        "keywords": "student laptop,university,laptop prices,portable,battery",
        "related_category_keywords": "laptop,notebook,macbook",
        "body": "Start with the course requirements\n\nAsk which applications the course uses. A student writing assignments and attending online classes needs less graphics power than a student running engineering, architecture, statistics or media software. Buy for the actual software, not only for a processor badge.\n\nPrioritise practical specifications\n\nAn SSD improves startup and application speed. Eight gigabytes of RAM can handle basic study work, while sixteen gigabytes gives more room for demanding software and multitasking. Confirm the processor generation, screen, webcam, Wi-Fi, keyboard and available ports.\n\nConsider daily movement\n\nA smaller laptop is easier to carry, but a larger screen may be more comfortable for design, spreadsheets and long reading sessions. Check the weight of both the laptop and charger.\n\nBudget beyond the laptop\n\nAllow for a protective sleeve, backup storage, software, maintenance and possible battery replacement. Request a receipt and understand the warranty before paying.",
    },
    {
        "slug": "laptop-prices-in-uganda-by-budget",
        "title": "Laptop Prices in Uganda by Budget",
        "excerpt": "Understand what different laptop budgets can realistically provide and where specification trade-offs usually appear.",
        "keywords": "laptop prices,budget laptop,Uganda",
        "related_category_keywords": "laptop,notebook",
        "body": "Use price ranges as a starting point\n\nA budget is useful, but it should not replace the specification checklist. Two laptops at a similar price can have different processor generations, SSD sizes, battery condition, screen quality and warranty.\n\nEntry-level priorities\n\nFor basic office and school work, prioritise a reliable SSD, enough RAM and a keyboard and battery that are in usable condition. Avoid paying mainly for appearance while accepting very old hardware.\n\nMid-range priorities\n\nA stronger processor, sixteen gigabytes of RAM, a larger SSD and a better display can improve useful life. Business-class refurbished models may compete with newer consumer models, but condition must be documented.\n\nPerformance budgets\n\nEngineering, design, editing and gaming may require dedicated graphics, stronger cooling and a high-wattage charger. Compare the exact graphics model and workload requirements.\n\nAlways compare total cost\n\nInclude accessories, delivery, setup, software, upgrades and warranty in the final decision.",
    },
    {
        "slug": "dell-latitude-buying-guide",
        "title": "Dell Latitude Buying Guide",
        "excerpt": "Understand Dell Latitude series, generations, business features and the checks needed when buying refurbished units.",
        "keywords": "Dell Latitude,Dell laptop,business laptop",
        "related_category_keywords": "laptop,notebook",
        "body": "Latitude is a business family, not one specification\n\nDell Latitude models cover different sizes, performance levels and generations. Read the complete model number and processor, not only the Latitude name.\n\nCheck the configuration\n\nConfirm processor generation, RAM, SSD, screen resolution, touchscreen status, keyboard layout, webcam, Wi-Fi and ports. Some models have soldered memory or limited upgrade options.\n\nInspect refurbished units\n\nTest hinges, keyboard, trackpad, USB ports, charging, speakers, camera and display. Review battery information and confirm that a suitable Dell charger is included.\n\nChoose according to use\n\nPortable 7000-series models may suit travel, while larger or more serviceable models can suit office deployment. Precision is normally the better Dell family for workstation workloads.",
    },
    {
        "slug": "hp-elitebook-generation-guide",
        "title": "HP EliteBook Generation Guide",
        "excerpt": "Compare HP EliteBook generations and configurations without relying on the EliteBook name alone.",
        "keywords": "HP EliteBook,HP laptop,generation",
        "related_category_keywords": "laptop,notebook",
        "body": "Read the full model name\n\nEliteBook model numbers identify size and generation. A newer generation normally brings newer processors and platform features, but the exact configuration still matters.\n\nCompare the essentials\n\nCheck processor generation, memory capacity and upgradeability, SSD, screen, ports, keyboard and battery note. Some slim models use more soldered components.\n\nMatch the series to the work\n\nSmaller models support portability. Larger models may offer more ports or screen space. ZBook is HP's workstation line for heavier graphics and technical workloads.\n\nInspect condition honestly\n\nFor refurbished equipment, verify the case, hinges, keyboard, display, battery and charger and request clear condition notes.",
    },
    {
        "slug": "thinkpad-vs-elitebook-vs-latitude",
        "title": "ThinkPad vs EliteBook vs Latitude",
        "excerpt": "Compare three established business-laptop families by keyboard, serviceability, portability and configuration.",
        "keywords": "ThinkPad,EliteBook,Latitude,business laptop comparison",
        "related_category_keywords": "laptop,notebook",
        "body": "All three are broad product families\n\nThinkPad, EliteBook and Latitude include many series and generations. A comparison must use exact models, not brand reputation alone.\n\nKeyboard and usability\n\nThinkPad is strongly associated with its keyboard design. EliteBook and Latitude also provide professional keyboards, but layout and feel differ by model. Test the exact unit where possible.\n\nServiceability and upgrades\n\nSome generations allow easy RAM, SSD and battery service, while thinner models use soldered components. Check the maintenance options before purchase.\n\nPerformance and portability\n\nProcessor, cooling, RAM, SSD and display matter more than the family name. Compare the configuration required for the work, then use build, ports, warranty and price to decide.",
    },
    {
        "slug": "how-to-inspect-a-refurbished-laptop",
        "title": "How to Inspect a Refurbished Laptop",
        "excerpt": "A practical inspection checklist covering identity, specifications, display, keyboard, battery, ports and documentation.",
        "keywords": "refurbished laptop,used laptop inspection,battery health",
        "related_category_keywords": "laptop,notebook,macbook",
        "body": "Confirm identity first\n\nCheck the brand, full model, serial number and installed processor, RAM and storage. The physical unit should match the quotation and product description.\n\nInspect the body and display\n\nCheck cracks, dents, missing screws, hinges, rubber feet, screen marks, dead pixels and brightness. Confirm touchscreen operation where applicable.\n\nTest every input and connection\n\nUse the keyboard, trackpad, webcam, microphone, speakers, Wi-Fi, Bluetooth, USB ports, video ports and audio jack. Test charging and confirm the charger rating.\n\nReview storage and battery\n\nCheck SSD health and battery information using appropriate diagnostic tools. Battery runtime varies with age and workload, so use an honest test note rather than a guarantee based only on percentage.\n\nProtect the transaction\n\nRequest a receipt, written warranty terms and clear condition information. Keep the serial number on the documentation.",
    },
    {
        "slug": "ssd-vs-hdd",
        "title": "SSD vs HDD: Which Storage Should You Choose?",
        "excerpt": "Compare speed, durability, capacity and cost when choosing computer storage.",
        "keywords": "SSD,HDD,storage upgrade",
        "related_category_keywords": "storage,laptop,desktop",
        "body": "An SSD is normally the best system drive\n\nSolid-state drives start the computer and applications faster and have no moving mechanical parts. They are a strong upgrade for many older computers.\n\nHDD still offers economical capacity\n\nHard disk drives can provide large storage at a lower cost per gigabyte. They remain useful for archives and backups where speed is less important.\n\nUse both where appropriate\n\nA desktop can use an SSD for the operating system and applications and a larger HDD for files. Important data should still be backed up because any drive can fail.\n\nCheck compatibility\n\nConfirm physical size, connector and supported interface before buying an upgrade.",
    },
    {
        "slug": "8gb-vs-16gb-ram",
        "title": "8GB vs 16GB RAM",
        "excerpt": "Choose memory capacity according to applications, multitasking and upgradeability.",
        "keywords": "8GB RAM,16GB RAM,memory upgrade",
        "related_category_keywords": "laptop,desktop,memory",
        "body": "Eight gigabytes supports basic work\n\nDocuments, browsing, email and online classes can run well on eight gigabytes when the system also has a suitable processor and SSD. Heavy browser use can still consume much of it.\n\nSixteen gigabytes provides more working space\n\nIt is useful for heavier multitasking, large spreadsheets, programming tools, statistics, virtual meetings, design and many professional applications.\n\nMore RAM does not fix every bottleneck\n\nA very old processor, failing storage or poor cooling can remain slow even with more memory. Evaluate the full system.\n\nCheck upgradeability\n\nSome laptops have soldered memory. Confirm whether additional RAM can be installed before buying.",
    },
    {
        "slug": "computers-for-accounting-engineering-and-design",
        "title": "Best Computers for Accounting, Engineering and Graphic Design",
        "excerpt": "Match processor, memory, storage and graphics to professional applications instead of buying one generic business computer.",
        "keywords": "accounting computer,engineering laptop,graphic design laptop,workstation",
        "related_category_keywords": "laptop,desktop,workstation",
        "body": "Accounting and office systems\n\nPrioritise a dependable processor, SSD, enough RAM for spreadsheets and accounting software, a comfortable screen and reliable backup. Check compatibility with the exact accounting package.\n\nEngineering systems\n\nEngineering applications may require stronger processors, more memory and certified or dedicated graphics. Use the software publisher's current requirements as a starting point.\n\nGraphic design and editing\n\nA quality display, adequate RAM, fast storage and suitable graphics improve the workflow. Colour-sensitive work may require an external calibrated display.\n\nAvoid one-size-fits-all recommendations\n\nList the exact applications and project sizes, then compare hardware and budget with room for future work.",
    },
    {
        "slug": "how-to-choose-a-router-in-uganda",
        "title": "How to Choose a Router in Uganda",
        "excerpt": "Select a router by internet source, coverage, users, Wi-Fi standard and building layout.",
        "keywords": "router Uganda,Wi-Fi router,4G router,5G router,mesh",
        "related_category_keywords": "router,networking,access point",
        "body": "Identify the internet source\n\nFibre or Ethernet service uses different equipment from a mobile 4G or 5G connection. A router without a cellular modem cannot use a SIM directly.\n\nEstimate users and traffic\n\nVideo calls, streaming, cloud backup and many connected devices need more capacity than light browsing. Check processor, Wi-Fi standard and Ethernet ports.\n\nPlan coverage\n\nWalls, floors and interference reduce signal. Place equipment centrally where possible. Larger buildings may need access points or mesh nodes connected by cable.\n\nConsider management and support\n\nGuest Wi-Fi, parental controls, traffic management, updates and available technical support can be more valuable than an exaggerated speed label.",
    },
    {
        "slug": "ups-buying-guide-for-unstable-power",
        "title": "UPS Buying Guide for Unstable Power",
        "excerpt": "Choose backup power by load, runtime, battery condition and the equipment that must shut down safely.",
        "keywords": "UPS,power backup,computer protection",
        "related_category_keywords": "ups,power,desktop,networking",
        "body": "Define the protected load\n\nList the computer, monitor, router, switch or other equipment that must remain powered. Do not size a UPS only by the desktop label.\n\nDecide the required runtime\n\nA UPS may provide enough time for safe shutdown or longer operation, depending on capacity and load. Longer runtime requires more battery capacity.\n\nProtect critical equipment\n\nUse suitable surge protection and proper electrical installation. Printers with heaters can draw high power and may not belong on a small UPS.\n\nMaintain the battery\n\nUPS batteries age and should be tested and replaced when capacity falls. Keep ventilation clear and document maintenance for business installations.",
    },
    {
        "slug": "laptop-battery-health-guide",
        "title": "Laptop Battery Health Guide",
        "excerpt": "Understand battery condition, runtime, heat and honest testing for new and refurbished laptops.",
        "keywords": "battery health,laptop battery,MacBook battery",
        "related_category_keywords": "laptop,macbook",
        "body": "Battery percentage is not battery health\n\nA battery showing one hundred percent charge can still have reduced capacity. Health information should be considered together with a practical runtime test.\n\nHeat accelerates ageing\n\nBlocked ventilation, heavy heat and unsuitable charging conditions can shorten battery life. Keep vents clear and avoid leaving a hot laptop inside a closed vehicle or bag.\n\nUse realistic expectations\n\nRuntime depends on screen brightness, applications, wireless use and battery age. Refurbished product pages should use a test note or range rather than a universal promise.\n\nPlan replacement\n\nBefore buying an older model, check whether a quality replacement battery is available and affordable.",
    },
    {
        "slug": "common-laptop-repair-problems",
        "title": "Common Laptop Repair Problems",
        "excerpt": "Recognise signs of storage failure, overheating, battery problems, charging faults and damaged displays.",
        "keywords": "laptop repair,overheating,battery,charging,SSD",
        "related_category_keywords": "repair,laptop,service",
        "body": "Slow performance\n\nSlow startup can come from failing storage, insufficient memory, background software, overheating or an old processor. Diagnose before replacing parts.\n\nOverheating and fan noise\n\nDust, blocked vents, failing fans, dried thermal material and heavy software load can raise temperatures. Continued overheating can damage components.\n\nBattery and charging faults\n\nA worn battery, damaged charger, charging port or motherboard circuit can cause similar symptoms. Use the correct charger and test the system.\n\nDisplay and hinge damage\n\nA cracked screen, damaged cable or hinge can worsen with use. Back up data and repair structural damage before it affects more components.\n\nProtect data first\n\nImportant files should be backed up before major repair or operating-system work.",
    },
    {
        "slug": "business-it-maintenance-checklist",
        "title": "Business IT Maintenance Checklist",
        "excerpt": "A practical maintenance routine for computers, backups, updates, networking, security and asset records.",
        "keywords": "business IT maintenance,computer maintenance,backup,security",
        "related_category_keywords": "service,networking,computer",
        "body": "Maintain an asset register\n\nRecord the user, model, serial number, purchase date, warranty, installed software and major repairs for each device.\n\nProtect and test backups\n\nBackups should run automatically where possible and restoration should be tested. One copy should be separated from the main computer or network.\n\nApply updates safely\n\nKeep operating systems, browsers, security tools and business applications supported and updated. Test major changes where business risk is high.\n\nInspect hardware and power\n\nClean ventilation, check storage health, review battery and UPS condition and replace damaged cables.\n\nReview accounts and access\n\nRemove departed users, use strong authentication, limit administrator rights and document ownership of shared services.\n\nSchedule professional review\n\nRegular preventive maintenance is normally less disruptive than waiting for complete failure.",
    },
    {
        "slug": "computer-procurement-guide-for-schools-and-ngos",
        "title": "Computer Procurement Guide for Schools and NGOs",
        "excerpt": "Plan specifications, quotations, warranties, delivery, asset records and support for accountable technology procurement.",
        "keywords": "computer procurement,school computers,NGO laptops,quotation",
        "related_category_keywords": "laptop,desktop,printer,networking",
        "body": "Define the use case and quantity\n\nList users, applications, locations, connectivity and expected useful life. Avoid using one specification for every role when workloads differ.\n\nWrite measurable specifications\n\nState processor generation or performance class, minimum RAM, SSD, screen, ports, condition, operating system, warranty and included accessories. Allow equivalent models where appropriate.\n\nCompare total cost\n\nInclude delivery, installation, software, networking, power protection, training, maintenance and replacement parts. The lowest unit price may not provide the lowest total cost.\n\nRequire documentation\n\nUse a formal quotation, invoice, receipt, serial-number schedule, warranty terms and acceptance record. Inspect delivered equipment against the approved configuration.\n\nPlan support and disposal\n\nAssign asset responsibility, backup and security policies, preventive maintenance and an approved process for data wiping and disposal.",
    },
]


DELIVERY_ZONES = [
    {
        "name": "Kampala central delivery",
        "areas": "Central Kampala and nearby business districts",
        "lead_time": "Same day or next business day where stock and route permit",
        "notes": "The exact address, parcel size and delivery window must be confirmed before payment.",
        "sort_order": 1,
    },
    {
        "name": "Greater Kampala delivery",
        "areas": "Wakiso, Mukono and surrounding Greater Kampala locations",
        "lead_time": "Normally arranged after location and route confirmation",
        "notes": "Charges vary by exact destination and order size.",
        "sort_order": 2,
    },
    {
        "name": "Upcountry delivery",
        "areas": "Major towns and other Uganda destinations served through an agreed courier or transport method",
        "lead_time": "Confirmed according to destination and carrier",
        "notes": "Products, serials, packaging, recipient details and carrier responsibility should be confirmed before dispatch.",
        "sort_order": 3,
    },
    {
        "name": "Store or agreed-point collection",
        "areas": "Collection from the confirmed LEOSOFT location or another documented handover point",
        "lead_time": "After stock and payment or quotation approval",
        "notes": "Carry the order or quotation reference and verify the product before accepting handover.",
        "sort_order": 4,
    },
]


class Command(BaseCommand):
    help = "Seed the editable commercial landing pages, FAQs, guides and delivery zones."

    def add_arguments(self, parser):
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="Refresh seeded fields and FAQs. Without this flag, staff edits are preserved.",
        )

    def handle(self, *args, **options):
        refresh = options["refresh"]
        pages_created = pages_updated = 0
        faqs_created = 0
        for payload in PAGES:
            faq_rows = payload.pop("faqs")
            slug = payload["slug"]
            page, created = CommercialLandingPage.objects.get_or_create(
                slug=slug,
                defaults=payload,
            )
            if created:
                pages_created += 1
            elif refresh:
                for field, value in payload.items():
                    setattr(page, field, value)
                page.save()
                pages_updated += 1
            if created or refresh or not page.faqs.exists():
                if refresh:
                    page.faqs.all().delete()
                if not page.faqs.exists():
                    CommercialLandingFAQ.objects.bulk_create(
                        [
                            CommercialLandingFAQ(
                                page=page,
                                question=question,
                                answer=answer,
                                sort_order=index,
                            )
                            for index, (question, answer) in enumerate(faq_rows, start=1)
                        ]
                    )
                    faqs_created += len(faq_rows)
            payload["faqs"] = faq_rows

        guides_created = guides_updated = 0
        for payload in GUIDES:
            slug = payload["slug"]
            guide, created = BuyingGuide.objects.get_or_create(slug=slug, defaults=payload)
            if created:
                guides_created += 1
            elif refresh:
                for field, value in payload.items():
                    setattr(guide, field, value)
                guide.save()
                guides_updated += 1

        zones_created = zones_updated = 0
        for payload in DELIVERY_ZONES:
            name = payload["name"]
            zone, created = DeliveryZone.objects.get_or_create(name=name, defaults=payload)
            if created:
                zones_created += 1
            elif refresh:
                for field, value in payload.items():
                    setattr(zone, field, value)
                zone.save()
                zones_updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Commercial growth seed complete: "
                f"pages {pages_created} created/{pages_updated} refreshed, "
                f"FAQs {faqs_created}, guides {guides_created} created/{guides_updated} refreshed, "
                f"delivery zones {zones_created} created/{zones_updated} refreshed."
            )
        )
