#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sincroniza los bloques compartidos del sitio: el menú, el pie y la ficha de
identidad del schema. Corre en la Mac, sobre los archivos del repo, y lo que
se commitea es el HTML ya escrito. No instala nada: solo Python 3.

    python3 tools/sync-bloques.py            # muestra qué cambiaría, no escribe
    python3 tools/sync-bloques.py --escribir # escribe los archivos

Los bloques canónicos viven en tools/bloques/. Para cambiar el menú se edita
tools/bloques/nav.html una vez y se corre el script.
"""

import re
import sys
import json
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SITIO = RAIZ / "Site"
BLOQUES = pathlib.Path(__file__).resolve().parent / "bloques"

# ---------------------------------------------------------------- páginas ---
# Para cada archivo, qué enlace del menú queda marcado como página actual.
# None = ninguno. Los archivos que no figuran acá no se tocan.
PAGINA_ACTUAL = {
    "index.html": None,
    "liderazgo.html": "/liderazgo.html",
    "transicion.html": "/transicion.html",
    "ejecutivo.html": "/ejecutivo.html",
    "enfoque.html": "/enfoque.html",
    "liderazgo-en-panama.html": None,   # página de referencia, no está en el menú
    "privacidad.html": None,
    "404.html": None,                  # página de error, tampoco está en el menú
    "blog/index.html": "/blog/",
}
# Todos los artículos del blog marcan Blog.
for _p in sorted(SITIO.glob("blog/*.html")):
    _rel = f"blog/{_p.name}"
    PAGINA_ACTUAL.setdefault(_rel, "/blog/")

# agenda.html y gracias.html llevan un menú reducido a propósito: quedan fuera.
SIN_MENU = {"agenda.html", "gracias.html"}

# La plantilla de artículos nuevos vive fuera de Site/ y también se sincroniza,
# para que el próximo artículo no nazca con el menú viejo.
PLANTILLA = RAIZ / "TXT" / "post-template.html"

SERVICIOS = {"/liderazgo.html", "/transicion.html", "/ejecutivo.html"}

# Dos piezas del menú y del pie son distintas a propósito y se declaran acá:
# el home lleva el logotipo dibujado y el claim de marca; el resto, el logo de
# texto y el pie sin claim. Todo lo demás es una sola fuente.
LOGO = {"index.html": "logo-home.html"}
MARCA = {"index.html": "marca-home.html"}

RE_NAV = re.compile(r"<nav>.*?</nav>", re.S)
RE_FOOTER = re.compile(r"<!-- FOOTER · bloque canónico A45.*?<!-- /FOOTER -->", re.S)
RE_JSONLD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def poner_slots(html: str, rel: str) -> str:
    """Rellena los huecos declarados: <!--LOGO--> en el menú, <!--MARCA--> en el pie."""
    if "<!--LOGO-->" in html:
        pieza = (BLOQUES / LOGO.get(rel, "logo.html")).read_text(encoding="utf-8").strip()
        html = html.replace("<!--LOGO-->", pieza)
    if "<!--MARCA-->" in html:
        pieza = (BLOQUES / MARCA.get(rel, "marca.html")).read_text(encoding="utf-8").strip()
        html = html.replace("<!--MARCA-->", pieza)
    return html


def marcar_actual(nav: str, destino: str | None) -> str:
    """Devuelve el menú canónico con la página actual marcada.

    Regla: los enlaces de primer nivel del menú de escritorio usan class="active";
    los del submenú y los del menú móvil usan aria-current="page". Si el destino
    es una página de servicio, el padre "Servicios" también queda activo.
    """
    if destino is None:
        return nav

    partes = nav.split('<div class="nav-mobile"')
    escritorio = partes[0]
    movil = '<div class="nav-mobile"' + partes[1] if len(partes) > 1 else ""

    def con_clase(html: str, href: str) -> str:
        return html.replace(f'<a href="{href}"', f'<a href="{href}" class="active"', 1)

    def con_aria(html: str, href: str, veces: int = 0) -> str:
        return html.replace(f'<a href="{href}"', f'<a href="{href}" aria-current="page"', veces or -1)

    if destino in SERVICIOS:
        escritorio = con_clase(escritorio, "/#servicios")
        escritorio = con_aria(escritorio, destino)
        movil = con_aria(movil, destino)
    else:
        escritorio = con_clase(escritorio, destino)
        movil = con_aria(movil, destino)

    return escritorio + movil


def id_person(texto: str) -> set:
    """Los @id que declara el nodo Person de un archivo, si lo tiene."""
    ids = set()
    for bloque in RE_JSONLD.findall(texto):
        try:
            datos = json.loads(bloque)
        except json.JSONDecodeError:
            return {"JSON-LD ROTO"}
        nodos = datos.get("@graph", [datos])
        for n in nodos:
            tipos = n.get("@type", "")
            tipos = tipos if isinstance(tipos, list) else [tipos]
            if "Person" in tipos:
                ids.add(n.get("@id", "sin @id"))
    return ids


def archivos():
    for rel in sorted(PAGINA_ACTUAL):
        yield SITIO / rel, rel, PAGINA_ACTUAL[rel]
    if PLANTILLA.exists():
        yield PLANTILLA, "TXT/post-template.html", "/blog/"


def main() -> int:
    escribir = "--escribir" in sys.argv
    nav_canon = (BLOQUES / "nav.html").read_text(encoding="utf-8").strip()
    pie_canon = (BLOQUES / "footer.html").read_text(encoding="utf-8").strip()

    cambios, problemas, ids = 0, [], {}

    for ruta, rel, destino in archivos():
        if not ruta.exists():
            problemas.append(f"{rel}: no existe")
            continue
        original = ruta.read_text(encoding="utf-8")
        texto = original

        navs = RE_NAV.findall(texto)
        if len(navs) != 1:
            problemas.append(f"{rel}: encontré {len(navs)} bloques <nav>, esperaba 1")
        else:
            nuevo_nav = poner_slots(marcar_actual(nav_canon, destino), rel)
            texto = RE_NAV.sub(lambda _: nuevo_nav, texto, count=1)

        pies = RE_FOOTER.findall(texto)
        if len(pies) != 1:
            problemas.append(f"{rel}: encontré {len(pies)} bloques de pie, esperaba 1")
        else:
            nuevo_pie = poner_slots(pie_canon, rel)
            texto = RE_FOOTER.sub(lambda _: nuevo_pie, texto, count=1)

        p = id_person(texto)
        if p:
            ids[rel] = p

        if texto != original:
            cambios += 1
            que = []
            if RE_NAV.search(original) and RE_NAV.search(original).group(0).strip() != poner_slots(marcar_actual(nav_canon, destino), rel).strip():
                que.append("menú")
            if RE_FOOTER.search(original) and RE_FOOTER.search(original).group(0).strip() != poner_slots(pie_canon, rel).strip():
                que.append("pie")
            print(f"  {'escrito ' if escribir else 'cambiaría'}  {rel}  ({', '.join(que) or 'formato'})")
            if escribir:
                ruta.write_text(texto, encoding="utf-8")

    print()
    print(f"{cambios} archivo(s) {'escritos' if escribir else 'a cambiar'}.")

    # La ficha de identidad no se reescribe: se controla. Reescribir JSON dentro
    # del HTML reformatea el bloque entero y ensucia el diff; avisar alcanza.
    todos = set().union(*ids.values()) if ids else set()
    print(f"\nFicha de identidad (Person) en {len(ids)} archivo(s): ", end="")
    if len(todos) == 1:
        print(f"un solo @id, {todos.pop()}")
    else:
        print("ATENCIÓN, hay más de uno")
        for rel, v in sorted(ids.items()):
            print(f"    {rel}: {', '.join(sorted(v))}")

    if problemas:
        print("\nProblemas:")
        for x in problemas:
            print("   ", x)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
