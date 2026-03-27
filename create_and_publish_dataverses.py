#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd
import requests
import urllib3

# Suppress warnings for verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass
class UniDVConfig:
    csv_path: str
    base_url: str                 # e.g. https://datapublication-nrw-dev.hrz.uni-bonn.de
    parent_alias: str             # e.g. :root
    api_token: str                # REQUIRED (CLI param)
    fallback_contact_email: Optional[str] = None
    timeout_s: int = 30
    dry_run: bool = False
    ignore_ssl: bool = True       # ✅ ignore SSL cert validation


class DataverseProvisioner:
    """
    Creates + publishes Dataverse collections (dataverses) from a CSV.

    Endpoints (Dataverse Native API):
    - Create:  POST /api/dataverses/{parentAlias}
    - Publish: POST /api/dataverses/{alias}/actions/:publish
    """

    def __init__(self, cfg: UniDVConfig):
        self.cfg = cfg
        self.session = requests.Session()
        self.session.verify = (not self.cfg.ignore_ssl)  # ✅ ignore SSL if requested
        self.session.headers.update({
            "X-Dataverse-key": self.cfg.api_token,
            "Content-Type": "application/json",
        })

    def _url(self, path: str) -> str:
        return self.cfg.base_url.rstrip("/") + path

    def _req_kwargs(self) -> dict:
        # extra safety even though session.verify is set
        return {"timeout": self.cfg.timeout_s, "verify": (not self.cfg.ignore_ssl)}

    def dataverse_exists(self, alias: str) -> bool:
        r = self.session.get(self._url(f"/api/dataverses/{alias}"), **self._req_kwargs())
        if r.status_code == 200:
            return True
        if r.status_code == 404:
            return False
        raise RuntimeError(f"Unexpected response checking '{alias}': {r.status_code} {r.text[:300]}")

    def create_dataverse(self, alias: str, name: str, description: str, affiliation: str, contact_email: str) -> Dict[str, Any]:
        payload = {
            "name": name,
            "alias": alias,
            "affiliation": affiliation or "",
            "dataverseContacts": [{"contactEmail": contact_email}],
            "description": description or "",
            "dataverseType": "INSTITUTION",
        }

        if self.cfg.dry_run:
            return {"dry_run": True, "action": "create", "alias": alias, "payload": payload}

        r = self.session.post(
            self._url(f"/api/dataverses/{self.cfg.parent_alias}"),
            json=payload,
            **self._req_kwargs(),
        )
        if r.status_code != 200:
            raise RuntimeError(f"Create failed for '{alias}': {r.status_code} {r.text[:500]}")
        return r.json()

    def publish_dataverse(self, alias: str) -> Dict[str, Any]:
        if self.cfg.dry_run:
            return {"dry_run": True, "action": "publish", "alias": alias}

        r = self.session.post(
            self._url(f"/api/dataverses/{alias}/actions/:publish"),
            **self._req_kwargs(),
        )
        if r.status_code == 200:
            return r.json()

        # tolerate common "already published" / forbidden / conflict
        if r.status_code in (400, 403, 409):
            return {"status": "NOT_OK", "alias": alias, "http": r.status_code, "message": r.text[:500]}

        raise RuntimeError(f"Publish failed for '{alias}': {r.status_code} {r.text[:500]}")

    def provision_from_csv(self) -> Dict[str, Any]:
        df = pd.read_csv(self.cfg.csv_path, delimiter=",", quotechar='"')

        if "enabled" not in df.columns:
            raise SystemExit('CSV missing required column "enabled".')
        df = df[df["enabled"].astype(int) == 1]

        if "label" not in df.columns:
            raise SystemExit('CSV missing required column "label".')

        results = {
            "created": [],
            "skipped_existing": [],
            "published_ok": [],
            "published_warn": [],
            "errors": [],
        }

        for _, row in df.iterrows():
            alias = str(row.get("label", "")).strip()
            if not alias:
                continue

            name = str(row.get("Name", alias)).strip() or alias
            affiliation = str(row.get("affiliation", "")).strip()
            description = str(row.get("description", "")).strip()

            contact_email = str(row.get("contactEmail", "")).strip()
            if not contact_email:
                contact_email = (self.cfg.fallback_contact_email or "").strip()
            if not contact_email:
                results["errors"].append({
                    "alias": alias,
                    "error": "Missing contactEmail (CSV column contactEmail or --fallback_contact_email)."
                })
                continue

            try:
                if self.dataverse_exists(alias):
                    results["skipped_existing"].append(alias)
                else:
                    self.create_dataverse(alias, name, description, affiliation, contact_email)
                    results["created"].append(alias)

                pub = self.publish_dataverse(alias)
                if isinstance(pub, dict) and pub.get("status") == "NOT_OK":
                    results["published_warn"].append(pub)
                else:
                    results["published_ok"].append(alias)

            except Exception as e:
                results["errors"].append({"alias": alias, "error": str(e)})

        return results


def main():
    ap = argparse.ArgumentParser(description="Create and publish Dataverse collections from unis.csv (enabled==1).")
    ap.add_argument("--server_name", required=True, help="e.g. datapublication-nrw-dev.hrz.uni-bonn.de (without https://)")
    ap.add_argument("--api_token", required=True, help="Dataverse API token (required)")
    ap.add_argument("--csv_path", required=True, help="Path to unis.csv")
    ap.add_argument("--parent_alias", default=":root", help="Parent dataverse alias, default :root")
    ap.add_argument("--fallback_contact_email", default=None, help="Used if CSV has no contactEmail column/value")
    ap.add_argument("--timeout_s", type=int, default=30)
    ap.add_argument("--dry_run", action="store_true", help="Do not call API, just show intent.")
    ap.add_argument("--ignore_ssl", action="store_true", help="Ignore SSL cert validation (self-signed dev certs).")
    args = ap.parse_args()

    server = args.server_name.strip().removeprefix("https://").removeprefix("http://").strip("/")
    base_url = f"http://{server}"

    cfg = UniDVConfig(
        csv_path=args.csv_path,
        base_url=base_url,
        parent_alias=args.parent_alias,
        api_token=args.api_token,
        fallback_contact_email=args.fallback_contact_email,
        timeout_s=args.timeout_s,
        dry_run=args.dry_run,
        ignore_ssl=args.ignore_ssl or True,  # default True if you always want it ignored
    )

    prov = DataverseProvisioner(cfg)
    res = prov.provision_from_csv()

    print("\n=== Provisioning summary ===")
    print(f"Created: {len(res['created'])}")
    print(f"Skipped existing: {len(res['skipped_existing'])}")
    print(f"Published OK: {len(res['published_ok'])}")
    print(f"Published warnings: {len(res['published_warn'])}")
    print(f"Errors: {len(res['errors'])}")

    if res["published_warn"]:
        print("\n--- Publish warnings (non-fatal) ---")
        for w in res["published_warn"]:
            print(f"- {w.get('alias')}: HTTP {w.get('http')} {w.get('message')}")

    if res["errors"]:
        print("\n--- Errors ---")
        for e in res["errors"]:
            print(f"- {e.get('alias')}: {e.get('error')}")


if __name__ == "__main__":
    main()
