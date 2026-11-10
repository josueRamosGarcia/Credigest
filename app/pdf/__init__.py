"""Generacion de documentos PDF.

Usa WeasyPrint para convertir plantillas HTML (Jinja2) en PDF. La ventaja frente
a dibujar coordenadas a mano es que el diseno vive en CSS y se puede ajustar sin
tocar Python.

Reglas que aplican:
- RN-27/RN-28: el pagare incluye datos del cliente, condiciones, clausula de
  mora y tabla de amortizacion completa (docs/01-requisitos.md).
- RNF-27: el documento indica que es un apoyo y no sustituye asesoria legal.
"""
