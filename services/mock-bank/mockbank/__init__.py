"""Mock bank issuer (simulation only).

Stands in for a bank's authorised confirmation channel in the prototype: it signs FDR
credentials with a per-bank Ed25519 key and keeps a status registry that records lien
removal and closure (N3). It never represents a real bank.
"""
