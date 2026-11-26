"""Pack previously verified reimbursement PDFs from an explicit UTF-8 JSON manifest.

Manifest: {"groups": [{"name": "ZIP stem", "total": "46.18",
"invoices": [{"id": "unique invoice ID", "amount": "46.18", "path": "invoice.pdf"}],
"trips": [{"invoice_ids": ["unique invoice ID"], "path": "details.zip",
"member": "trans.pdf", "name": "trip.pdf"}]}]}.
Invoice name is optional. Trip member is only for a source ZIP. Each PDF entry
accepts an optional sha256 of the exact PDF bytes. Resolve relative paths below
--source-root. An absolute source path is accepted only inside that root.
The caller verifies invoice IDs, amounts and trip links from the source documents.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
from lzma import LZMAError
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import unicodedata
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo
from zlib import error as ZlibError


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def name_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def safe_filename(name: str) -> str:
    require(isinstance(name, str) and bool(name) and name == name.strip(), "Expected a nonempty filename")
    require(not name.endswith(".") and not re.search(r'[<>:"/\\|?*\x00-\x1f]', name), f"Invalid filename: {name}")
    require(not re.fullmatch(r"(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])", name.split(".")[0], re.I), f"Reserved filename: {name}")
    return name


def money(value: str) -> Decimal:
    require(isinstance(value, str) and bool(re.fullmatch(r"-?[0-9]+(?:\.[0-9]{1,2})?", value)), f"Expected amount as a decimal string: {value!r}")
    return Decimal(value)


def directory(value: Path) -> Path:
    require(value.is_absolute() and value.is_dir(), f"Expected an existing absolute directory: {value}")
    return value.resolve()


def read_pdf(entry: dict, root: Path, *, permit_zip: bool) -> tuple[Path, bytes]:
    path = (root / entry["path"]).resolve(strict=True)
    require(path.is_relative_to(root) and path.is_file(), f"Source file outside the authorized folder: {path}")
    member = entry.get("member")
    if member is None:
        require(path.suffix.lower() == ".pdf", f"Expected a PDF source: {path.name}")
        data = path.read_bytes()
    else:
        require(permit_zip and path.suffix.lower() == ".zip", "ZIP members are only allowed for trip PDFs")
        require(isinstance(member, str) and bool(member), "A ZIP member must be an exact PDF member name")
        for part in member.split("/"):
            safe_filename(part)
        require(PurePosixPath(member).suffix.lower() == ".pdf", f"Expected a PDF member: {member}")
        with ZipFile(path) as source:
            matches = [info for info in source.infolist() if info.filename == member]
            require(len(matches) == 1, f"Expected one ZIP member {member!r} in {path.name}")
            info = matches[0]
            require(not info.is_dir() and not stat.S_ISLNK(info.external_attr >> 16) and not (info.flag_bits & 1),
                    f"Expected an ordinary unencrypted ZIP member: {member}")
            data = source.read(info)

    require(data.startswith(b"%PDF-") and data.rstrip(b"\x00\t\n\f\r ").endswith(b"%%EOF"),
            f"The source does not have a complete PDF header and trailer: {member or path.name}")
    if "sha256" in entry:
        expected = entry["sha256"]
        require(isinstance(expected, str) and sha256(data).hexdigest() == expected.lower(),
                f"PDF content changed since verification: {member or path.name}")
    return path, data


def entries_for(group: dict, root: Path, seen_ids: set[str]) -> dict[str, bytes]:
    invoices = group["invoices"]
    trips = group.get("trips", [])
    require(isinstance(invoices, list) and bool(invoices), "At least one invoice is required per group")
    require(isinstance(trips, list), "Trips must be an array")
    members: dict[str, bytes] = {}
    seen_names: set[str] = set()
    group_ids: set[str] = set()
    total = Decimal(0)

    def add(folder: str, filename: str, data: bytes) -> None:
        safe_filename(filename)
        require(Path(filename).suffix.lower() == ".pdf", f"Expected a PDF filename: {filename}")
        member = f"{folder}/{filename}"
        key = name_key(member)
        require(key not in seen_names, f"Duplicate ZIP entry: {member}")
        seen_names.add(key)
        members[member] = data

    for invoice in invoices:
        identity = invoice["id"]
        require(isinstance(identity, str) and bool(identity) and identity == identity.strip(), "Invoice ID must be nonempty text")
        require(identity not in seen_ids, f"Repeated invoice ID across packages: {identity}")
        seen_ids.add(identity)
        group_ids.add(identity)
        total += money(invoice["amount"])
        path, data = read_pdf(invoice, root, permit_zip=False)
        add("发票", invoice.get("name", path.name), data)
    require(total == money(group["total"]), f"Invoice amounts do not reconcile for {group['name']}: {total:.2f}")

    for trip in trips:
        ids = trip["invoice_ids"]
        require(isinstance(ids, list) and bool(ids) and all(isinstance(key, str) and key in group_ids for key in ids),
                f"Trip PDF references an unlisted invoice: {trip['name']}")
        _, data = read_pdf(trip, root, permit_zip=True)
        add("高速费行程单", trip["name"], data)
    return members


def create_verified_zip(path: Path, entries: dict[str, bytes]) -> str:
    names = sorted(entries)
    with ZipFile(path, "x") as archive:
        for name in names:
            archive.writestr(ZipInfo(name), entries[name], compress_type=ZIP_DEFLATED, compresslevel=6)
    with ZipFile(path) as archive:
        require(archive.namelist() == names and archive.testzip() is None, f"ZIP verification failed: {path.name}")
        for name in names:
            require(sha256(archive.read(name)).digest() == sha256(entries[name]).digest(), f"PDF changed in ZIP: {name}")
    return sha256(path.read_bytes()).hexdigest()


def verify_destination(path: Path, staged: Path, staged_digest: str) -> str:
    require(not path.is_symlink() and path.is_file(), f"Unexpected output path: {path}")
    content = path.read_bytes()
    actual_digest = sha256(content).hexdigest()
    if actual_digest == staged_digest:
        return actual_digest

    conflict = f"Existing ZIP differs or cannot be verified, kept intact: {path}"
    try:
        with ZipFile(BytesIO(content)) as existing, ZipFile(staged) as expected:
            members = sorted(expected.namelist())
            matches = (
                sorted(existing.namelist()) == members
                and not any(stat.S_ISLNK(info.external_attr >> 16) for info in existing.infolist())
                and all(existing.read(name) == expected.read(name) for name in members)
            )
    except (BadZipFile, EOFError, LZMAError, OSError, RuntimeError, ValueError, ZlibError) as error:
        raise ValueError(conflict) from error
    require(matches, conflict)
    return actual_digest


def pack(manifest: Path, root: Path, output: Path) -> list[dict]:
    data = json.loads(manifest.read_text(encoding="utf-8-sig"))
    groups = data["groups"]
    require(isinstance(groups, list) and bool(groups), "Manifest must include at least one group")
    seen_ids: set[str] = set()
    names: set[str] = set()
    results: list[dict] = []

    with tempfile.TemporaryDirectory(dir=output) as temporary:
        stage = Path(temporary)
        for group in groups:
            stem = safe_filename(group["name"])
            require(not stem.lower().endswith(".zip"), f"Group name must omit the ZIP extension: {stem}")
            filename = f"{stem}.zip"
            key = name_key(filename)
            require(key not in names, f"Repeated ZIP filename: {filename}")
            names.add(key)
            members = entries_for(group, root, seen_ids)
            staged = stage / filename
            digest = create_verified_zip(staged, members)
            destination = output / filename
            if destination.exists() or destination.is_symlink():
                verify_destination(destination, staged, digest)
            results.append({"name": filename, "total": f"{money(group['total']):.2f}",
                            "pdf_count": len(members), "sha256": digest})

        for result in results:
            staged = stage / result["name"]
            destination = output / result["name"]
            try:
                if os.name == "nt":
                    staged.rename(destination)
                else:
                    os.link(staged, destination)
            except FileExistsError:
                pass
            result["sha256"] = verify_destination(destination, staged, result["sha256"])

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        results = pack(args.manifest, directory(args.source_root), directory(args.output_dir))
    except (BadZipFile, KeyError, OSError, TypeError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
