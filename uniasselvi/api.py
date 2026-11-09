"""Cliente da API do AVA2 (Uniasselvi).

Endpoints descobertos do bundle JS do próprio AVA2:
  - POST https://api-areasegura.uniasselvi.com.br/security/check      {username, password} -> {token}
  - POST https://api-areasegura.uniasselvi.com.br/user/specialization {userAuth}           -> lista de cursos
  - POST https://api-areasegura.uniasselvi.com.br/user/data           {userAuth, specialization} -> dados do aluno
  - POST https://api-ava.uniasselvi.com.br/test/pendent/get           -> provas/trabalhos pendentes
  - POST https://api-ava.uniasselvi.com.br/academic/production/get    -> produções (trabalhos entregues)
  - POST https://api-ava.uniasselvi.com.br/complementary-activities/get -> atividades complementares
  - POST https://api-ava.uniasselvi.com.br/calendar/event/get_by_studant -> agenda do semestre
Autenticação: header  Authorization: Bearer <token>  (cookie uniToken no domínio uniasselvi.com.br).
"""
import json
import os
import time

import requests

from .config import APP_DIR

BASE_AREASEGURA = "https://api-areasegura.uniasselvi.com.br"
BASE_AVA = "https://api-ava.uniasselvi.com.br"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

DEBUG_DIR = os.path.join(APP_DIR, "debug")


class AuthError(Exception):
    pass


class ApiError(Exception):
    pass


class UniAPI:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://areasegura.uniasselvi.com.br",
            "Referer": "https://areasegura.uniasselvi.com.br/",
        })
        self.token = None

    # ---------------- helpers ----------------
    def _post(self, url, payload, tries=3):
        last = None
        for i in range(tries):
            try:
                r = self.s.post(url, json=payload, timeout=30)
            except requests.RequestException as e:
                last = e
                time.sleep(2 * (i + 1))
                continue
            if r.status_code == 401:
                msg = "Não autorizado"
                try:
                    msg = r.json().get("message") or msg
                except Exception:
                    pass
                raise AuthError(msg)
            if r.status_code >= 400:
                raise ApiError(f"HTTP {r.status_code} em {url}: {r.text[:300]}")
            if r.status_code == 204 or not r.text.strip():
                return []  # 204 No Content = nada para este aluno/parâmetro
            try:
                return r.json()
            except ValueError:
                raise ApiError(f"Resposta não-JSON de {url}: {r.text[:200]}")
        raise ApiError(f"Falha de rede chamando {url}: {last}")

    def _dump(self, name, data):
        """Salva a resposta bruta para depagem (debug/)."""
        try:
            os.makedirs(DEBUG_DIR, exist_ok=True)
            with open(os.path.join(DEBUG_DIR, f"{name}.json"), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------------- auth ----------------
    def login(self, username, password):
        data = self._post(f"{BASE_AREASEGURA}/security/check",
                          {"username": username, "password": password})
        token = None
        if isinstance(data, dict):
            token = data.get("token") or (data.get("data") or {}).get("token")
        if not token:
            self._dump("login_raw", data)
            raise AuthError("Login respondeu sem token — veja debug/login_raw.json")
        self.token = token
        self.s.headers["Authorization"] = f"Bearer {token}"
        self.s.cookies.set("uniToken", token, domain=".uniasselvi.com.br", path="/")
        self.s.cookies.set("userAuth", "ALUN", domain=".uniasselvi.com.br", path="/")
        return data

    def get_specializations(self, user_auth="ALUN"):
        data = self._post(f"{BASE_AREASEGURA}/user/specialization",
                          {"userAuth": user_auth, "noCache": True})
        self._dump("specializations", data)
        return data

    def get_user_data(self, user_auth="ALUN", specialization=""):
        data = self._post(f"{BASE_AREASEGURA}/user/data",
                          {"userAuth": user_auth, "specialization": specialization})
        self._dump("user_data", data)
        return data

    # ---------------- dados acadêmicos ----------------
    def _ava_payload(self, specialization, modality, area=None, **extra):
        p = {"specialization": specialization, "modality": modality, "noCache": True}
        if area:
            p["area"] = area
        p.update(extra)
        return p

    def pending_tests(self, specialization, modality, area=None):
        data = self._post(f"{BASE_AVA}/test/pendent/get",
                          self._ava_payload(specialization, modality, area))
        self._dump("pending_tests", data)
        return data

    def subjects(self, specialization, modality, area, semester):
        data = self._post(f"{BASE_AVA}/academic/subject/get",
                          self._ava_payload(specialization, modality, area,
                                            semester=semester))
        self._dump("subjects", data)
        return data

    def tests_for_subject(self, specialization, modality, area, semester,
                          subject_code, class_code, course_code):
        data = self._post(f"{BASE_AVA}/test/get",
                          self._ava_payload(specialization, modality, area,
                                            semester=semester,
                                            subjectCode=subject_code,
                                            classCode=class_code,
                                            courseCode=course_code))
        self._dump(f"tests_{subject_code}", data)
        return data

    def productions(self, specialization, modality, area=None):
        data = self._post(f"{BASE_AVA}/academic/production/get",
                          self._ava_payload(specialization, modality, area))
        self._dump("productions", data)
        return data

    def complementary_activities(self, specialization, modality, area=None):
        data = self._post(f"{BASE_AVA}/complementary-activities/get",
                          self._ava_payload(specialization, modality, area))
        self._dump("complementary", data)
        return data

    def calendar_events(self, specialization, modality, semester):
        data = self._post(f"{BASE_AVA}/calendar/event/get_by_studant",
                          {"specialization": specialization, "semester": semester,
                           "modality": modality, "noCache": True})
        self._dump("calendar", data)
        return data
