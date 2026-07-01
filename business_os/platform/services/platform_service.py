"""Business OS Platform v1.0 — platform service.

This endpoint proves the skeleton is installed and describes how future features should be built.
"""

from __future__ import annotations

from business_os.platform.services.base import BaseService


class PlatformService(BaseService):
    version = "platform-1.0"

    @classmethod
    def status(cls):
        return cls.response(
            payload={
                "platform": "Business OS Platform",
                "architecture": {
                    "flow": [
                        "Route",
                        "Service",
                        "Engine",
                        "Repository",
                        "Database",
                    ],
                    "intelligence_flow": [
                        "Registry",
                        "Events",
                        "Evidence",
                        "Scores",
                        "Genome",
                        "Executive Brain",
                        "Mission Control",
                        "Execution",
                    ],
                },
                "subsystems": {
                    "registry": "Canonical identity and digital twin",
                    "executive": "Reasoning, scoring, strategy, recommendations",
                    "execution": "Approved actions and automation",
                    "evidence": "Explainability layer",
                    "scoring": "Reusable score framework",
                    "events": "Business timeline and memory foundation",
                },
                "rule": "No intelligence should live directly inside endpoints. Routes call services; services call engines; engines use repositories.",
            }
        )
