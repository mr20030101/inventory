"""HTTPS for sharing SAIMS on a local network without a certificate authority.

The computer that shares SAIMS creates its own certificate once and keeps it in the data folder. Other
computers are shown the certificate's fingerprint the first time they connect; once someone confirms it matches
the code shown on the sharing computer, that exact certificate is remembered ("pinned"). Later connections are
only accepted with that certificate, so passwords cannot be read or intercepted on the network.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import ipaddress
import os
import socket
import ssl
from pathlib import Path

DEFAULT_PORT = 8765


def ensure_certificate(folder: Path, common_name: str = "SAIMS") -> tuple[Path, Path]:
    """Return (certificate, private key) paths, creating a self-signed pair on first use."""
    cert_path, key_path = folder / "server.crt", folder / "server.key"
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    folder.mkdir(parents=True, exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name[:64]),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SAIMS")])
    hosts = {"localhost", socket.gethostname()}
    ips = {"127.0.0.1", *lan_addresses()}
    alt = [x509.DNSName(h) for h in sorted(hosts) if h] + [x509.IPAddress(ipaddress.ip_address(i)) for i in sorted(ips)]
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName(alt), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, content_commitment=False,
                                         key_encipherment=False, data_encipherment=False, key_agreement=False,
                                         crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(key, hashes.SHA256()))
    key_bytes = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption())
    # Write the key readable by this user only.
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(key_bytes)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


def fingerprint(cert_pem: str) -> str:
    """SHA-256 fingerprint of a PEM certificate, as hex."""
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert_pem)).hexdigest().upper()


def short_code(cert_pem: str) -> str:
    """Twelve characters people can read aloud and compare, e.g. 4F2A-9C1B-77E0."""
    fp = fingerprint(cert_pem)
    return f"{fp[0:4]}-{fp[4:8]}-{fp[8:12]}"


def pinned_context(cert_pem: str) -> ssl.SSLContext:
    """TLS context that trusts exactly this certificate and nothing else.

    The host name is not checked because computers on a school network often change address; the pinned
    certificate itself is the identity, and no other certificate (even a publicly trusted one) is accepted."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(cadata=cert_pem)
    return ctx


def fetch_certificate(host: str, port: int, timeout: float = 5.0) -> str:
    """Download a server's certificate without trusting it (used to show its fingerprint for confirmation)."""
    return ssl.get_server_certificate((host, port), timeout=timeout)


def lan_addresses() -> list[str]:
    """IPv4 addresses other computers on the local network can probably use to reach this one, best first.

    Container bridges (Docker/Podman, x.x.0.1 in 172.16.0.0/12), documentation test ranges and loopback
    addresses are left out."""
    found: list[str] = []
    try:  # UDP "connect" sends nothing; it only picks the outgoing interface
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 53))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    bridges = ipaddress.ip_network("172.16.0.0/12")
    test_nets = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")]
    out = []
    for addr in found:
        ip = ipaddress.ip_address(addr)
        if ip.is_loopback or ip.is_link_local or ip.is_unspecified or not ip.is_private:
            continue
        if any(ip in n for n in test_nets) or (ip in bridges and addr.endswith(".0.1")):
            continue
        if addr not in out:
            out.append(addr)
    # Office and home networks usually use 192.168.x.x, then 10.x.x.x (also common for VPNs), then 172.16–31.
    rank = {"192.168.": 0, "10.": 1}
    return sorted(out, key=lambda a: next((v for k, v in rank.items() if a.startswith(k)), 2))


def is_certificate_error(exc: BaseException) -> bool:
    """True if a connection failed because the server's certificate is not trusted."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(exc):
            return True
        exc = exc.__cause__ or exc.__context__
    return False
