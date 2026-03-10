"""
Seed mock data for the 4-table structure.

Setup:
  orders/
    management/
      __init__.py
      commands/
        __init__.py
        seed_data.py    <-- this file

Run:
  python manage.py seed_data
"""

from datetime import date
from django.core.management.base import BaseCommand
from orders.models import Patient, Provider, Order, CarePlan


class Command(BaseCommand):
    help = "Seed database with mock data"

    def handle(self, *args, **options):
        # Clear existing data (order matters because of foreign keys)
        CarePlan.objects.all().delete()
        Order.objects.all().delete()
        Patient.objects.all().delete()
        Provider.objects.all().delete()
        self.stdout.write("Cleared existing data.")

        # ===== Patients =====
        patients = [
            Patient.objects.create(
                first_name="John", last_name="Smith",
                mrn="MRN-001", dob=date(1979, 6, 8),
            ),
            Patient.objects.create(
                first_name="Maria", last_name="Garcia",
                mrn="MRN-002", dob=date(1985, 3, 15),
            ),
            Patient.objects.create(
                first_name="James", last_name="Chen",
                mrn="MRN-003", dob=date(1992, 11, 22),
            ),
            Patient.objects.create(
                first_name="Sarah", last_name="Johnson",
                mrn="MRN-004", dob=date(1988, 7, 4),
            ),
            Patient.objects.create(
                first_name="David", last_name="Kim",
                mrn="MRN-005", dob=date(1975, 1, 30),
            ),
        ]

        # ===== Providers =====
        providers = [
            Provider.objects.create(
                first_name="Emily", last_name="Wang", npi="1234567890",
            ),
            Provider.objects.create(
                first_name="Michael", last_name="Brown", npi="9876543210",
            ),
            Provider.objects.create(
                first_name="Lisa", last_name="Patel", npi="5551234567",
            ),
        ]

        # ===== Orders + CarePlans =====
        orders_data = [
            # John Smith - 3 orders (same patient, different meds/doctors)
            {
                "patient": patients[0], "provider": providers[0],
                "medication": "Metformin 500mg",
                "diagnosis": "Type 2 Diabetes",
                "medical_history": "Diagnosed in 2019. On metformin since 2020.",
                "care_plan_content": "Take metformin twice daily with meals. Monitor blood sugar weekly. Follow up in 3 months.",
                "care_plan_status": "completed",
            },
            {
                "patient": patients[0], "provider": providers[0],
                "medication": "Lisinopril 10mg",
                "diagnosis": "Hypertension",
                "medical_history": "BP elevated at last visit. Starting ACE inhibitor.",
                "care_plan_content": "Take once daily in the morning. Monitor BP at home. Report dizziness.",
                "care_plan_status": "completed",
            },
            {
                "patient": patients[0], "provider": providers[1],
                "medication": "Atorvastatin 20mg",
                "diagnosis": "High cholesterol",
                "medical_history": "LDL 165. Lifestyle changes insufficient.",
                "care_plan_content": "",
                "care_plan_status": "pending",
            },
            # Maria Garcia - 2 orders
            {
                "patient": patients[1], "provider": providers[1],
                "medication": "Amlodipine 5mg",
                "diagnosis": "Hypertension",
                "medical_history": "Family history of heart disease. BP controlled with medication.",
                "care_plan_content": "Take once daily. Avoid grapefruit. Check BP twice weekly.",
                "care_plan_status": "completed",
            },
            {
                "patient": patients[1], "provider": providers[1],
                "medication": "Hydrochlorothiazide 25mg",
                "diagnosis": "Hypertension",
                "medical_history": "Adding diuretic for better BP control.",
                "care_plan_content": "",
                "care_plan_status": "processing",
            },
            # James Chen - 1 order
            {
                "patient": patients[2], "provider": providers[2],
                "medication": "Albuterol Inhaler",
                "diagnosis": "Asthma",
                "medical_history": "Childhood asthma. Uses inhaler as needed.",
                "care_plan_content": "Use 2 puffs as needed for shortness of breath. Max 8 puffs per day.",
                "care_plan_status": "completed",
            },
            # Sarah Johnson - 2 orders
            {
                "patient": patients[3], "provider": providers[0],
                "medication": "Escitalopram 10mg",
                "diagnosis": "Depression",
                "medical_history": "Diagnosed 2021. Switched from sertraline.",
                "care_plan_content": "Take once daily in the morning. May cause initial drowsiness. Follow up in 4 weeks.",
                "care_plan_status": "completed",
            },
            {
                "patient": patients[3], "provider": providers[2],
                "medication": "Trazodone 50mg",
                "diagnosis": "Insomnia",
                "medical_history": "Sleep difficulty related to depression treatment.",
                "care_plan_content": "Patient reported adverse reaction. Discontinue and consult provider.",
                "care_plan_status": "failed",
            },
            # David Kim - 2 orders
            {
                "patient": patients[4], "provider": providers[2],
                "medication": "Ibuprofen 600mg",
                "diagnosis": "Chronic back pain",
                "medical_history": "L4-L5 disc herniation. Physical therapy ongoing.",
                "care_plan_content": "Take with food, 3 times daily as needed. Max 7 days without follow-up.",
                "care_plan_status": "completed",
            },
            {
                "patient": patients[4], "provider": providers[1],
                "medication": "Cyclobenzaprine 10mg",
                "diagnosis": "Muscle spasm",
                "medical_history": "Related to chronic back pain. Adding muscle relaxant.",
                "care_plan_content": "",
                "care_plan_status": "pending",
            },
        ]

        for o in orders_data:
            order = Order.objects.create(
                patient=o["patient"],
                provider=o["provider"],
                medication=o["medication"],
                diagnosis=o["diagnosis"],
                medical_history=o["medical_history"],
            )
            CarePlan.objects.create(
                order=order,
                content=o["care_plan_content"],
                status=o["care_plan_status"],
            )
            self.stdout.write(f"  Created order #{order.id} + care plan")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Done! Seeded:"))
        self.stdout.write(f"  {Patient.objects.count()} patients")
        self.stdout.write(f"  {Provider.objects.count()} providers")
        self.stdout.write(f"  {Order.objects.count()} orders")
        self.stdout.write(f"  {CarePlan.objects.count()} care plans")