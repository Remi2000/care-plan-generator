import re
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from datetime import datetime, date
from typing import Optional


# ============================================================
# InternalOrder: 系统内部的标准格式
# 不管上游数据长什么样，所有 adapter 最终都翻译成这个格式
# 然后交给 create_order_service() 处理
# ============================================================

@dataclass
class InternalOrder:
    # Patient 信息
    mrn: str
    patient_first_name: str
    patient_last_name: str
    dob: Optional[date] = None

    # Provider 信息
    npi: str = ""
    provider_first_name: str = ""
    provider_last_name: str = ""

    # Order 信息
    medication: str = ""
    diagnosis: str = ""
    medical_history: str = ""

    # 控制字段
    confirm: bool = False

    def to_dict(self):
        """转成 dict，这样 create_order_service 可以直接用"""
        return asdict(self)


# ============================================================
# BaseIntakeAdapter: 抽象基类（模板）
# 规定所有 adapter 必须有 parse() 和 transform()
# validate() 是共用的，只写一遍
# ============================================================

class BaseIntakeAdapter(ABC):

    @abstractmethod
    def parse(self, raw_data):
        """解析原始数据（JSON、XML 等），存到 self 上"""
        pass

    @abstractmethod
    def transform(self) -> InternalOrder:
        """把解析后的数据翻译成 InternalOrder 标准格式"""
        pass

    def validate(self, order: InternalOrder):
        """所有数据源共用的验证逻辑，只写一遍"""

        # NPI 必须 10 位数字
        if not order.npi.isdigit() or len(order.npi) != 10:
            raise ValueError("NPI must be exactly 10 digits")

        # MRN 必须 6 位数字
        if not order.mrn.isdigit() or len(order.mrn) != 6:
            raise ValueError("MRN must be exactly 6 digits")

        # ICD-10 格式检查
        if order.diagnosis:
            for code in order.diagnosis.split(", "):
                if not re.match(r'^[A-Z]\d{2}(\.\d{1,2})?$', code):
                    raise ValueError(f"Invalid ICD-10 code: {code}")

    def process(self, raw_data):
        """
        统一入口：parse → transform → validate → 返回 dict
        views.py 只需要调这一个方法
        """
        self.parse(raw_data)
        order = self.transform()
        self.validate(order)
        return order.to_dict()


# ============================================================
# ClinicAdapter: 处理小型诊所的 JSON 数据
# ============================================================

class ClinicAdapter(BaseIntakeAdapter):

    def parse(self, raw_data):
        """原始数据就是 dict，直接存起来"""
        self.raw = raw_data
        return self

    def transform(self) -> InternalOrder:
        """把诊所的 JSON 格式翻译成 InternalOrder"""
        pt = self.raw["pt"]
        provider = self.raw["provider"]
        dx = self.raw["dx"]

        # provider 名字是 "Dr. Emily Johnson"，拆成 first 和 last
        name_parts = provider["name"].replace("Dr. ", "").split()

        # diagnosis: primary + secondary 合并成字符串
        all_dx = [dx["primary"]] + dx["secondary"]

        # dob 格式转换: "03/22/1985" → date 对象
        dob = datetime.strptime(pt["dob"], "%m/%d/%Y").date()

        return InternalOrder(
            mrn=pt["mrn"],
            patient_first_name=pt["fname"],
            patient_last_name=pt["lname"],
            dob=dob,
            npi=provider["npi_num"],
            provider_first_name=name_parts[0],
            provider_last_name=name_parts[-1],
            medication=self.raw["rx"]["med_name"],
            diagnosis=", ".join(all_dx),
            medical_history="\n".join(self.raw["med_hx"]),
        )


# ============================================================
# PharmaAdapter: 处理合作药企的 XML 数据
# ============================================================

class PharmaAdapter(BaseIntakeAdapter):

    def parse(self, raw_data):
        """把 XML 字符串解析成 ElementTree 对象"""
        self.root = ET.fromstring(raw_data)
        return self

    def transform(self) -> InternalOrder:
        """把药企的 XML 格式翻译成 InternalOrder"""
        root = self.root

        # patient 信息
        mrn = root.find(".//MedicalRecordNumber").text
        patient_first_name = root.find(".//PatientName/FirstName").text
        patient_last_name = root.find(".//PatientName/LastName").text
        dob_str = root.find(".//DateOfBirth").text  # "1972-11-30"
        dob = datetime.strptime(dob_str, "%Y-%m-%d").date()

        # provider 名字是 "Dr. Michael Chen"，拆开
        full_name = root.find(".//PrescriberInformation/FullName").text
        name_parts = full_name.replace("Dr. ", "").split()
        npi = root.find(".//PrescriberInformation/NPINumber").text

        # medication
        medication = root.find(".//MedicationOrder/DrugName").text

        # diagnosis: primary + 所有 secondary 的 ICDCode
        primary_dx = root.find(".//PrimaryDiagnosis/ICDCode").text
        secondary_dx = [
            d.find("ICDCode").text
            for d in root.findall(".//SecondaryDiagnoses/Diagnosis")
        ]
        all_dx = [primary_dx] + secondary_dx

        # medical history: 每个药拼成 "Name Dosage Frequency"
        med_history_items = []
        for med in root.findall(".//MedicationHistory/Medication"):
            name = med.find("MedicationName").text
            dosage = med.find("Dosage").text
            freq = med.find("Frequency").text
            med_history_items.append(f"{name} {dosage} {freq}")

        return InternalOrder(
            mrn=mrn,
            patient_first_name=patient_first_name,
            patient_last_name=patient_last_name,
            dob=dob,
            npi=npi,
            provider_first_name=name_parts[0],
            provider_last_name=name_parts[-1],
            medication=medication,
            diagnosis=", ".join(all_dx),
            medical_history="\n".join(med_history_items),
        )
    
# ============================================================
# MetroAdapter: 处理 Metro General Hospital 的 JSON 数据
# ============================================================

class MetroAdapter(BaseIntakeAdapter):

    def parse(self, raw_data):
        """原始数据就是 dict，直接存起来"""
        self.raw = raw_data
        return self

    def transform(self) -> InternalOrder:
        """把 Metro Hospital 格式翻译成 InternalOrder"""
        patient = self.raw["patient"]
        doc = self.raw["referring_doc"]
        clinical = self.raw["clinical"]

        # 医生名字是 "Sarah Thompson, MD"，去掉 ", MD" 再 split
        name_parts = doc["full_name"].replace(", MD", "").split()

        # diagnosis: primary + additional 合并成字符串
        all_dx = [clinical["icd10_primary"]] + clinical["icd10_additional"]

        # dob 格式是 "1990-06-15"
        dob = datetime.strptime(patient["birth_date"], "%Y-%m-%d").date()

        # 用药历史: 每个是 dict，拼成 "Name Dose Frequency"
        med_history_items = []
        for med in self.raw["current_medications"]:
            med_history_items.append(f"{med['name']} {med['dose']} {med['frequency']}")

        return InternalOrder(
            mrn=patient["medical_id"],
            patient_first_name=patient["name_first"],
            patient_last_name=patient["name_last"],
            dob=dob,
            npi=doc["national_provider_id"],
            provider_first_name=name_parts[0],
            provider_last_name=name_parts[-1],
            medication=self.raw["prescription"]["drug"],
            diagnosis=", ".join(all_dx),
            medical_history="\n".join(med_history_items),
        )

# ============================================================
# 工厂函数: 根据数据来源返回对应的 adapter
# 新增数据源只需要：1) 写一个 Adapter 类  2) 在这里加一行
# ============================================================

def get_adapter(source: str) -> BaseIntakeAdapter:
    adapters = {
        "clinic": ClinicAdapter,
        "pharma": PharmaAdapter,
        "metro": MetroAdapter,
    }

    adapter_class = adapters.get(source)
    if not adapter_class:
        raise ValueError(f"Unknown source: {source}")

    return adapter_class()