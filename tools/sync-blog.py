#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sincroniza todo lo que se deriva de un artículo del blog.

El artículo es la única fuente. De su HTML salen el título, la descripción,
la fecha, la portada y la categoría, y con eso este script escribe los cuatro
archivos que hasta ahora se editaban a mano:

    Site/articles.json          la lista que alimenta el blog y el home
    Site/blog/index.html        las tarjetas estáticas de respaldo
    Site/index.html             las dos tarjetas del home
    Site/sitemap.xml            las URLs de los artículos

    python3 tools/sync-blog.py             # muestra qué cambiaría, no escribe
    python3 tools/sync-blog.py --escribir  # escribe

Los artículos publicados fuera del sitio (La Estrella, Medium) no tienen
archivo del que leer, así que viven declarados en tools/externos.json.

Es idempotente: la segunda corrida da cero cambios.
"""

import re
import io
import sys
import json
import html
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SITIO = RAIZ / "Site"
EXTERNOS = pathlib.Path(__file__).resolve().parent / "externos.json"
BASE = "https://www.adriandeyme.com"

ICONO = {"Medium": "✦", "LinkedIn": "◆", "La Estrella de Panamá": "◈", "Blog": "◉"}
MES = ["ene", "feb", "mar", "abr", "may", "jun",
       "jul", "ago", "sept", "oct", "nov", "dic"]

MARCAS = {
    "tarjetas": ("<!-- TARJETAS · bloque generado por tools/sync-blog.py · no editar a mano -->",
                 "<!-- /TARJETAS -->"),
    "slots":    ("<!-- BLOG-SLOTS · bloque generado por tools/sync-blog.py · no editar a mano -->",
                 "<!-- /BLOG-SLOTS -->"),
    "articulos": ("<!-- ARTICULOS · bloque generado por tools/sync-blog.py · no editar a mano -->",
                  "<!-- /ARTICULOS -->"),
}

errores, avisos = [], []


# ------------------------------------------------------------------ leer ---

def _buscar(patron, texto, archivo, que, flags=0):
    m = re.search(patron, texto, flags)
    if not m:
        errores.append(f"{archivo}: no encontré {que}")
        return None
    return m.group(1).strip()


def _texto(bruto):
    """Quita etiquetas y resuelve entidades. Devuelve texto plano."""
    if bruto is None:
        return None
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", bruto))).strip()


def leer_articulo(ruta):
    """Lee un artículo y devuelve su ficha, o None si le falta algo."""
    s = ruta.read_text(encoding="utf-8")
    rel = f"blog/{ruta.name}"

    ficha = {
        "source": "Blog",
        "title": _texto(_buscar(r"<h1[^>]*>(.*?)</h1>", s, rel, "el H1", re.S)),
        "date": (_buscar(r'<meta property="article:published_time" content="(.*?)"', s, rel,
                         "la fecha (article:published_time)") or "")[:10],
        "slug": f"/blog/{ruta.name}",
        "img": _buscar(r'<meta property="og:image" content="(.*?)"', s, rel, "la portada (og:image)"),
        "desc": _texto(_buscar(r'<meta name="description" content="(.*?)"', s, rel, "la descripción", re.S)),
        "category": (_buscar(r'<meta property="article:section" content="(.*?)"', s, rel,
                             "la categoría (article:section)") or "").lower(),
    }

    # La dirección declarada tiene que ser la del archivo: es el error clásico
    # de partir de la plantilla o de otro artículo y olvidarse de cambiarla.
    esperada = f"{BASE}/blog/{ruta.name}"
    for etiqueta, patron in [
        ("canonical", r'<link rel="canonical" href="(.*?)"'),
        ("og:url", r'<meta property="og:url" content="(.*?)"'),
    ]:
        v = _buscar(patron, s, rel, etiqueta)
        if v and v != esperada:
            errores.append(f"{rel}: {etiqueta} apunta a {v}, debería ser {esperada}")
    if s.count(f'hreflang="es" href="{esperada}"') != 1 or s.count(f'hreflang="x-default" href="{esperada}"') != 1:
        errores.append(f"{rel}: los hreflang no apuntan a su propia dirección")

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", ficha["date"] or ""):
        errores.append(f"{rel}: la fecha no se pudo leer")
    if ficha["category"] not in {"liderazgo", "transicion", "herramientas", "coaching"}:
        errores.append(f"{rel}: categoría desconocida: {ficha['category']!r}")

    portada = SITIO / (ficha["img"] or "").replace(BASE + "/", "")
    if ficha["img"] and not portada.exists():
        errores.append(f"{rel}: la portada {ficha['img']} no existe en el repo")

    titulo_tag = _texto(_buscar(r"<title>(.*?)</title>", s, rel, "el <title>", re.S)) or ""
    if len(titulo_tag) > 65:
        avisos.append(f"{rel}: el <title> tiene {len(titulo_tag)} caracteres (más de 65 se corta en Google)")
    # Los marcadores solo importan si llegan al lector: dentro de un comentario
    # son instrucciones de la plantilla y no se ven.
    visible = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    if "[DD de mes" in visible or "[REEMPLAZAR" in visible:
        errores.append(f"{rel}: quedó un marcador de la plantilla sin reemplazar, y se ve")

    return ficha


def fichas():
    """Todas las fichas, las del blog y las externas, de más nueva a más vieja."""
    lista = []
    for ruta in sorted(SITIO.glob("blog/*.html")):
        if ruta.name == "index.html":
            continue
        lista.append(leer_articulo(ruta))

    if EXTERNOS.exists():
        externas = json.loads(EXTERNOS.read_text(encoding="utf-8"))
        for e in externas:
            if not e.get("url"):
                errores.append("externos.json: una entrada no tiene url")
            lista.append(e)

    lista.sort(key=lambda a: a["date"], reverse=True)

    vistos = {}
    for a in lista:
        k = a.get("slug") or a.get("url")
        if k in vistos:
            errores.append(f"dirección repetida: {k}")
        vistos[k] = a
    return lista


# --------------------------------------------------------------- escribir ---

def fecha_corta(iso):
    a, m, d = iso.split("-")
    return f"{d} {MES[int(m) - 1]} {a}"


def at(t):
    return html.escape(t or "", quote=True)


def tx(t):
    return html.escape(t or "", quote=False)


def tarjeta_listado(a):
    href = a.get("slug") or a["url"]
    fuera = "" if a.get("slug") else ' target="_blank" rel="noopener"'
    icono = ICONO.get(a["source"], "◇")
    portada = (
        f'<img src="{at(a["img"])}" alt="{at(a["title"])}" class="post-img" loading="lazy" '
        f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'">\n'
        f'        <div class="post-placeholder" style="display:none"><span class="post-placeholder-icon">{icono}</span></div>'
        if a.get("img") else
        f'<div class="post-placeholder"><span class="post-placeholder-icon">{icono}</span></div>'
    )
    return f"""      <article class="post-card" data-category="{at(a['category'])}">
        {portada}
        <div class="post-body">
          <div class="post-meta">
            <span class="post-source">{tx(a['source'])}</span>
            <span class="post-category">{tx(a['category'])}</span>
          </div>
          <h2 class="post-titulo">
            <a href="{at(href)}"{fuera}>{tx(a['title'])}</a>
          </h2>
          <p class="post-desc">{tx(a['desc'])}</p>
          <div class="post-footer">
            <span class="post-fecha">{fecha_corta(a['date'])}</span>
            <a href="{at(href)}"{fuera} class="post-link">Leer<span class="sr-only"> {tx(a['title'])}</span> <span aria-hidden="true">→</span></a>
          </div>
        </div>
      </article>"""


def tarjeta_home(a, n):
    return f"""      <article id="blog-dynamic-{n}" class="post-card reveal rd{n}">
        <img src="{at(a['img'])}" alt="{at(a['title'])}" class="post-img" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">
        <div class="post-placeholder" style="display:none"><span class="post-placeholder-icon">◉</span></div>
        <div class="post-body">
          <span class="post-source">Blog</span>
          <h3 class="post-titulo">
            <a href="{at(a['slug'])}" style="color:inherit;">{tx(a['title'])}</a>
          </h3>
          <p class="post-desc">{tx(a['desc'])}</p>
          <div class="post-footer">
            <span class="post-fecha">{fecha_corta(a['date'])}</span>
            <a href="{at(a['slug'])}" class="post-link">Leer<span class="sr-only"> {tx(a['title'])}</span> <span aria-hidden="true">→</span></a>
          </div>
        </div>
      </article>"""


def url_sitemap(a):
    return f"""  <url>
    <loc>{BASE}{a['slug']}</loc>
    <lastmod>{a['date']}</lastmod>
    <changefreq>yearly</changefreq>
    <priority>0.6</priority>
  </url>"""


def reemplazar_bloque(texto, marca, contenido, archivo):
    abre, cierra = MARCAS[marca]
    if texto.count(abre) != 1 or texto.count(cierra) != 1:
        errores.append(f"{archivo}: no encontré los marcadores de {marca}")
        return texto
    patron = re.compile(re.escape(abre) + r".*?" + re.escape(cierra), re.S)
    return patron.sub(lambda _: f"{abre}\n{contenido}\n      {cierra}"
                      if marca != "articulos" else f"{abre}\n{contenido}\n  {cierra}", texto, count=1)


# ------------------------------------------------------------------ main ---

def main() -> int:
    escribir = "--escribir" in sys.argv
    lista = fichas()
    if errores:
        print("No escribo nada. Hay que arreglar esto primero:\n")
        for e in errores:
            print("   ", e)
        return 1

    propios = [a for a in lista if a.get("slug")]
    del_blog = [a for a in lista if a["source"] == "Blog"][:2]

    salidas = {}

    # 1 · articles.json
    salidas[SITIO / "articles.json"] = json.dumps(lista, ensure_ascii=False, indent=2) + "\n"

    # 2 · las tarjetas del listado
    p = SITIO / "blog" / "index.html"
    s = p.read_text(encoding="utf-8")
    salidas[p] = reemplazar_bloque(s, "tarjetas",
                                   "\n\n".join(tarjeta_listado(a) for a in lista), "blog/index.html")

    # 3 · las dos tarjetas del home
    p = SITIO / "index.html"
    s = p.read_text(encoding="utf-8")
    salidas[p] = reemplazar_bloque(s, "slots",
                                   "\n".join(tarjeta_home(a, i + 1) for i, a in enumerate(del_blog)), "index.html")

    # 4 · el mapa del sitio
    p = SITIO / "sitemap.xml"
    s = p.read_text(encoding="utf-8")
    s = reemplazar_bloque(s, "articulos", "\n".join(url_sitemap(a) for a in propios), "sitemap.xml")
    if propios:
        s = re.sub(r"(<loc>" + re.escape(BASE) + r"/blog/</loc>\s*<lastmod>)\d{4}-\d{2}-\d{2}",
                   lambda m: m.group(1) + propios[0]["date"], s, count=1)
    salidas[p] = s

    if errores:
        print("No escribo nada:")
        for e in errores:
            print("   ", e)
        return 1

    cambios = 0
    for ruta, nuevo in salidas.items():
        rel = ruta.relative_to(RAIZ)
        if ruta.read_text(encoding="utf-8") == nuevo:
            continue
        cambios += 1
        print(f"  {'escrito  ' if escribir else 'cambiaría'}  {rel}")
        if escribir:
            ruta.write_text(nuevo, encoding="utf-8")

    print(f"\n{len(propios)} artículo(s) propio(s) y {len(lista) - len(propios)} externo(s).")
    print(f"{cambios} archivo(s) {'escritos' if escribir else 'a cambiar'}.")
    if avisos:
        print("\nAvisos (no impiden escribir):")
        for a in avisos:
            print("   ", a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
