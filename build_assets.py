#!/usr/bin/env python3
"""
build_assets.py — gera os SVGs do perfil (observatório espacial de software).

Por que um gerador?
  A esfera do hero é uma projeção 3D real (meridianos que giram, nós na
  superfície, anéis orbitais com oclusão). Esses números não dá para
  escrever à mão. Os SVGs em ../assets já estão prontos: você só precisa
  rodar este script se quiser mudar textos, cores ou a geometria.

Uso:
  python3 tools/build_assets.py                 # escreve em ../assets
  python3 tools/build_assets.py --freeze 90     # QA: quadro estático em t=90s
                                                #   -> ../assets/_preview/

Onde editar (tudo no bloco CONFIG logo abaixo):
  - NAME / TITLE / TITLE_2       nome e cargos
  - TICKER                       frases que se alternam sob o nome
  - ORBIT_LABELS                 tecnologias que orbitam a esfera
  - PALETTE                      cores
  - SECTIONS                     títulos das réguas de seção

Compatibilidade com o GitHub (por que é feito assim):
  - SVG puro, sem <script>, sem fontes web, sem imagens externas.
  - Animação via SMIL (<animate>), que roda dentro de <img> no GitHub.
  - Fontes: só pilhas de fontes do sistema (o GitHub bloqueia fontes web
    dentro de SVG).
"""
import argparse
import bisect
import math
import pathlib
import random

# ══════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════
NAME = "MATEUS PETRIS"
TITLE = "SOFTWARE ENGINEER"
TITLE_2 = "BACKEND DEVELOPER"
STATION_LEFT = "SOFTWARE OBSERVATORY"
# Vitória, ES (coordenadas reais da cidade, ~20°19′S 40°20′W)
STATION_RIGHT = "VITÓRIA  ·  20°19′S  40°20′W"

# Linhas que se alternam sob o nome (substitui a antiga "typing animation")
TICKER = [
    "Information Systems student · FAESA",
    "Vitória, Espírito Santo · Brazil",
    "Building backend systems with Java and Spring Boot",
]
TICKER_SECONDS_EACH = 5.0

PALETTE = dict(
    space="#05070D",     # deep space
    deep="#0D1117",      # azul escuro
    cyan="#7FDBFF",      # azul estelar
    violet="#9B8AFB",    # violeta discreto
    text="#EEF3F9",
    muted="#8B98A9",
    dim="#5B6878",
)

SANS = "'Inter','SF Pro Display','Segoe UI','Helvetica Neue',Helvetica,Arial,sans-serif"
MONO = ("'JetBrains Mono','SF Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,"
        "'Liberation Mono','DejaVu Sans Mono',monospace")

# Anéis orbitais: (rx, ry, inclinação em graus, cor, tracejado, espessura, opacidade)
ORBITS = {
    "A": (462, 116, -11, "cyan", None, 1.0, 0.34),
    "B": (382, 90, 14, "violet", None, 1.0, 0.36),
    "C": (326, 60, -30, "cyan", "2 6", 1.0, 0.30),
    "D": (270, 48, 25, "violet", "1 5", 1.0, 0.32),
    "E": (430, 30, 3, "cyan", None, 0.8, 0.16),
}

# Tecnologias nos anéis: (texto, anel, ângulo β no anel [graus], subtítulo, haste)
#   β entre 0 e 180  = metade da FRENTE do anel (parte de baixo da elipse)
#   β entre 180 e 360 = metade de TRÁS (passa atrás da esfera)
#   haste: "up" desenha o texto acima do nó, "down" abaixo.
ORBIT_LABELS = [
    ("JAVA",        "A", 203, "core language",   "up"),
    ("DOCKER",      "D", 205, "containers",      "up"),
    ("BACKEND",     "C", 170, "REST APIs",       "down"),
    ("DATABASE",    "C", 350, "MySQL · MongoDB", "up"),
    ("ALGORITHMS",  "A", 340, "sorting · search", "up"),
    ("SPRING BOOT", "B", 350, "framework",       "down"),
]

# Satélites minúsculos que percorrem os anéis: (anel, β inicial, segundos/volta)
SATELLITES = [
    ("A", 300, 150), ("A", 120, 150), ("B", 60, 110), ("C", 250, 80),
    ("D", 330, 64), ("E", 20, 180),
]

SECTIONS = {
    "section-about": "ABOUT THE EXPLORER",
    "section-missions": "MISSION LOG",
    "section-transmission": "TRANSMISSION",
}

# ══════════════════════════════════════════════════════════════════════
# GEOMETRIA / CANVAS DO HERO
# ══════════════════════════════════════════════════════════════════════
W, H = 1200, 820
CX, CY = 600, 334          # centro da esfera
R = 202                    # raio da esfera
TILT = -18.0               # inclinação do eixo (graus)
E = math.radians(17)       # elevação da câmera (vemos o polo norte)
SPIN = 1.0                 # graus por segundo
N_MERIDIANS = 12
MERIDIAN_STEP = 360 / N_MERIDIANS
LOOP_MERIDIAN = MERIDIAN_STEP / SPIN     # 30 s: o conjunto se repete a cada 30°
LOOP_NODES = 360 / SPIN                  # 360 s: volta completa


def n(v, d=1):
    """Número compacto para SVG."""
    s = f"{v:.{d}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def bez_arc(c, U, V, t0, t1, nseg):
    """
    Caminho de Béziers cúbicas para a elipse  c + cos(t)·U + sin(t)·V,  t∈[t0,t1].
    Usar a mesma estrutura de comandos em todos os quadros permite que o
    navegador interpole o atributo `d` suavemente.
    """
    d = (t1 - t0) / nseg
    k = 4 / 3 * math.tan(d / 4)

    def P(t):
        return (c[0] + math.cos(t) * U[0] + math.sin(t) * V[0],
                c[1] + math.cos(t) * U[1] + math.sin(t) * V[1])

    def D(t):
        return (-math.sin(t) * U[0] + math.cos(t) * V[0],
                -math.sin(t) * U[1] + math.cos(t) * V[1])

    out = []
    for i in range(nseg):
        a = t0 + i * d
        b = a + d
        p0, p3 = P(a), P(b)
        d0, d3 = D(a), D(b)
        p1 = (p0[0] + k * d0[0], p0[1] + k * d0[1])
        p2 = (p3[0] - k * d3[0], p3[1] - k * d3[1])
        if i == 0:
            out.append(f"M{n(p0[0])} {n(p0[1])}")
        out.append(f"C{n(p1[0])} {n(p1[1])} {n(p2[0])} {n(p2[1])} {n(p3[0])} {n(p3[1])}")
    return "".join(out)


def surf(phi, lam, theta):
    """Ponto na esfera (lat φ, lon λ, giro θ) -> (x, y, profundidade), y para baixo."""
    l = lam + theta
    X = R * math.cos(phi) * math.sin(l)
    Y = R * math.sin(phi)
    Z = R * math.cos(phi) * math.cos(l)
    return X, Z * math.sin(E) - Y * math.cos(E), Y * math.sin(E) + Z * math.cos(E)


def facing(zp):
    """0 (atrás) .. 1 (de frente), transição suave perto do limbo."""
    o = max(0.0, min(1.0, (zp / R + 0.06) / 0.30))
    return o * o * (3 - 2 * o)


def meridian_arcs(L):
    """Arcos (frente, trás) do meridiano de longitude L, e o quanto ele encara a câmera."""
    A = (R * math.sin(L), R * math.cos(L) * math.sin(E))
    B = (0.0, -R * math.cos(E))
    ph = math.atan2(-math.cos(L) * math.cos(E), math.sin(E))   # horizonte do meridiano
    front = bez_arc((0, 0), A, B, ph, math.pi / 2, 2)
    back = bez_arc((0, 0), A, B, -math.pi / 2, ph, 2)
    return front, back, math.cos(L)


# ══════════════════════════════════════════════════════════════════════
# ÓRBITAS
# ══════════════════════════════════════════════════════════════════════
def ellipse_table(rx, ry, steps=1440):
    """Comprimento de arco acumulado por β (para posicionar satélites)."""
    betas = [2 * math.pi * i / steps for i in range(steps + 1)]
    cum = [0.0]
    for i in range(1, len(betas)):
        x0, y0 = rx * math.cos(betas[i - 1]), ry * math.sin(betas[i - 1])
        x1, y1 = rx * math.cos(betas[i]), ry * math.sin(betas[i])
        cum.append(cum[-1] + math.hypot(x1 - x0, y1 - y0))
    return betas, cum


def S_of(beta, table):
    betas, cum = table
    beta %= 2 * math.pi
    i = bisect.bisect_right(betas, beta) - 1
    i = min(i, len(betas) - 2)
    f = (beta - betas[i]) / (betas[i + 1] - betas[i])
    return cum[i] + f * (cum[i + 1] - cum[i])


def beta_of(s, table):
    betas, cum = table
    s %= cum[-1]
    i = bisect.bisect_right(cum, s) - 1
    i = min(i, len(cum) - 2)
    f = (s - cum[i]) / (cum[i + 1] - cum[i])
    return betas[i] + f * (betas[i + 1] - betas[i])


def ring_xy(key, beta_deg):
    """Posição absoluta (no canvas) de um ponto do anel."""
    rx, ry, rho = ORBITS[key][:3]
    b = math.radians(beta_deg)
    r = math.radians(rho)
    x, y = rx * math.cos(b), ry * math.sin(b)
    return CX + x * math.cos(r) - y * math.sin(r), CY + x * math.sin(r) + y * math.cos(r)


# ══════════════════════════════════════════════════════════════════════
# HERO
# ══════════════════════════════════════════════════════════════════════
def build_hero(freeze=None):
    anim = freeze is None
    t = 0.0 if anim else float(freeze)
    P = PALETTE
    rnd = random.Random(2026)
    o = []                      # linhas do SVG
    add = o.append

    # ── defs ──────────────────────────────────────────────────────────
    add(f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-labelledby="t d">
<title id="t">Mateus Petris — Software Engineer</title>
<desc id="d">Observatório espacial de software: uma esfera escura de linhas orbitais e nós girando lentamente, com as tecnologias Java, Spring Boot, Backend, Database, Docker e Algorithms em órbita.</desc>
<style>
  .sans{{font-family:{SANS}}}
  .mono{{font-family:{MONO}}}
</style>
<defs>
  <clipPath id="frame"><rect width="{W}" height="{H}" rx="18"/></clipPath>
  <radialGradient id="neb-violet" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="{P['violet']}" stop-opacity="0.10"/><stop offset="1" stop-color="{P['violet']}" stop-opacity="0"/></radialGradient>
  <radialGradient id="neb-cyan" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="{P['cyan']}" stop-opacity="0.07"/><stop offset="1" stop-color="{P['cyan']}" stop-opacity="0"/></radialGradient>
  <radialGradient id="halo" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#12233A" stop-opacity="0.55"/><stop offset="1" stop-color="#12233A" stop-opacity="0"/></radialGradient>
  <radialGradient id="atmo" cx="0.5" cy="0.5" r="0.5"><stop offset="{n(R/(R+46),3)}" stop-color="{P['cyan']}" stop-opacity="0.17"/><stop offset="1" stop-color="{P['cyan']}" stop-opacity="0"/></radialGradient>
  <radialGradient id="body" cx="0.36" cy="0.3" r="0.85"><stop offset="0" stop-color="#15243A"/><stop offset="0.55" stop-color="#0A111D"/><stop offset="1" stop-color="{P['space']}"/></radialGradient>
  <linearGradient id="shade" x1="0.22" y1="0.12" x2="0.95" y2="0.98"><stop offset="0" stop-color="{P['space']}" stop-opacity="0"/><stop offset="0.5" stop-color="{P['space']}" stop-opacity="0.10"/><stop offset="1" stop-color="{P['space']}" stop-opacity="0.78"/></linearGradient>
  <linearGradient id="rim" gradientUnits="userSpaceOnUse" x1="{-R}" y1="{-R}" x2="{R}" y2="{R}"><stop offset="0" stop-color="{P['cyan']}" stop-opacity="0.85"/><stop offset="0.5" stop-color="{P['cyan']}" stop-opacity="0.08"/><stop offset="1" stop-color="{P['violet']}" stop-opacity="0.25"/></linearGradient>
  <filter id="soft" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="5"/></filter>
  <filter id="glow" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="2.2"/></filter>
</defs>
<g clip-path="url(#frame)">
<rect width="{W}" height="{H}" fill="{P['space']}"/>''')

    # ── fundo: nebulosas discretas + halo atrás da esfera ─────────────
    add('<g id="nebula">')
    add(f'<ellipse cx="230" cy="640" rx="420" ry="240" fill="url(#neb-violet)"/>')
    add(f'<ellipse cx="1010" cy="170" rx="400" ry="230" fill="url(#neb-cyan)"/>')
    add(f'<circle cx="{CX}" cy="{CY}" r="430" fill="url(#halo)"/>')
    add('</g>')

    # ── estrelas ──────────────────────────────────────────────────────
    add('<g id="stars">')
    cols = ["#DDEBFF"] * 6 + ["#FFFFFF"] * 3 + ["#BFD8FF"] * 3 + ["#CDBEFF", "#FFE9CF"]
    twinkle_budget = 16
    for _ in range(240):
        x, y = rnd.uniform(14, W - 14), rnd.uniform(14, H - 14)
        if math.hypot(x - CX, y - CY) < R + 4:
            continue
        r = rnd.choices([0.35, 0.5, 0.7, 0.95, 1.3], [30, 30, 22, 12, 6])[0]
        op = rnd.uniform(0.25, 0.9) if r > 0.6 else rnd.uniform(0.18, 0.6)
        col = rnd.choice(cols)
        tw = ""
        if anim and r >= 0.7 and twinkle_budget > 0:
            twinkle_budget -= 1
            dur = rnd.uniform(3.5, 9)
            tw = (f'<animate attributeName="opacity" values="{n(op,2)};{n(op*0.28,2)};{n(op,2)}" '
                  f'dur="{n(dur)}s" begin="{n(rnd.uniform(0,4))}s" repeatCount="indefinite"/>')
        add(f'<circle cx="{n(x)}" cy="{n(y)}" r="{r}" fill="{col}" opacity="{n(op,2)}">{tw}</circle>' if tw
            else f'<circle cx="{n(x)}" cy="{n(y)}" r="{r}" fill="{col}" opacity="{n(op,2)}"/>')
    add('</g>')

    # duas estrelas com espículas de difração (referência ao James Webb)
    def spike_star(x, y, L, op):
        pts = []
        for ang in (90, 30, 150):
            for sgn in (1, -1):
                a = math.radians(ang) + (0 if sgn == 1 else math.pi)
                ex, ey = x + L * math.cos(a), y - L * math.sin(a)
                nx_, ny_ = -math.sin(a) * 0.9, -math.cos(a) * 0.9
                pts.append(f'<polygon points="{n(x+nx_)},{n(y+ny_)} {n(ex,1)},{n(ey,1)} {n(x-nx_)},{n(y-ny_)}"/>')
        for sgn in (1, -1):
            pts.append(f'<polygon points="{n(x)},{n(y-0.8)} {n(x+sgn*L*0.34)},{n(y)} {n(x)},{n(y+0.8)}"/>')
        return (f'<g fill="#DDEBFF" opacity="{op}">{"".join(pts)}</g>'
                f'<circle cx="{x}" cy="{y}" r="1.7" fill="#fff" opacity="0.95"/>'
                f'<circle cx="{x}" cy="{y}" r="5" fill="#BFD8FF" opacity="0.14"/>')
    add('<g id="webb-stars">' + spike_star(150, 168, 44, 0.42) + spike_star(1068, 612, 34, 0.34) + '</g>')

    # ── moldura de carta celeste: cantos e graduação nas bordas ──────
    m, L_ = 30, 20
    corners = (f'M{m} {m+L_}V{m}H{m+L_} M{W-m-L_} {m}H{W-m}V{m+L_} '
               f'M{W-m} {H-m-L_}V{H-m}H{W-m-L_} M{m+L_} {H-m}H{m}V{H-m-L_}')
    ticks = []
    for x in range(60, W - 40, 30):
        big = (x - 60) % 150 == 0
        L2 = 6 if big else 3
        ticks.append(f'M{x} 14v{L2}M{x} {H-14}v-{L2}')
    for y in range(60, H - 40, 30):
        big = (y - 60) % 150 == 0
        L2 = 6 if big else 3
        ticks.append(f'M14 {y}h{L2}M{W-14} {y}h-{L2}')
    add(f'<g id="chart-frame" fill="none" stroke="{P["cyan"]}" stroke-width="1">'
        f'<path d="{corners}" opacity="0.4"/><path d="{"".join(ticks)}" opacity="0.16"/></g>')

    # ── anéis: metade de TRÁS (fica sob a esfera) ────────────────────
    def ring_group(key, half):
        rx, ry, rho, colk, dash, sw, op = ORBITS[key]
        col = P[colk]
        if half == "front":
            d = f"M{rx} 0A{rx} {ry} 0 0 1 {-rx} 0"
            a = op
        else:
            d = f"M{-rx} 0A{rx} {ry} 0 0 1 {rx} 0"
            a = op * 0.55
        da = f' stroke-dasharray="{dash}"' if dash else ""
        return (f'<g transform="translate({CX} {CY}) rotate({rho})">'
                f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{sw}" opacity="{n(a,2)}"{da}/></g>')

    tables = {k: ellipse_table(v[0], v[1]) for k, v in ORBITS.items()}

    def satellite(key, beta0_deg, secs, half):
        """Satélite: cópia de 'frente' e de 'trás' com opacidade alternada nos extremos do anel."""
        rx, ry, rho, colk = ORBITS[key][:4]
        tb = tables[key]
        Ltot = tb[1][-1]
        b0 = math.radians(beta0_deg) % (2 * math.pi)
        s0 = S_of(b0, tb)
        if not anim:
            s = (s0 + Ltot * t / secs) % Ltot
            b = beta_of(s, tb)
            front = math.sin(b) > 0
            if (half == "front") != front:
                return ""
            x, y = rx * math.cos(b), ry * math.sin(b)
            return (f'<g transform="translate({CX} {CY}) rotate({rho})"><g transform="translate({n(x)} {n(y)})">'
                    f'<circle r="4.5" fill="{P[colk]}" opacity="0.18"/><circle r="1.9" fill="#fff" opacity="0.95"/></g></g>')
        x0, y0 = rx * math.cos(b0), ry * math.sin(b0)
        x1, y1 = rx * math.cos(b0 + math.pi), ry * math.sin(b0 + math.pi)
        path = f"M{n(x0)} {n(y0)}A{rx} {ry} 0 0 1 {n(x1)} {n(y1)}A{rx} {ry} 0 0 1 {n(x0)} {n(y0)}"
        # instantes (fração da volta) em que cruza β=0 e β=π
        ev = sorted(((S_of(bb, tb) - s0) % Ltot) / Ltot for bb in (0.0, math.pi))
        ev = [e for e in ev if 1e-4 < e < 1 - 1e-4]
        start_front = 1 if math.sin(b0) > 0 else 0
        want = start_front if half == "front" else 1 - start_front
        vals, kt, cur = [str(want)], ["0"], want
        for e in ev:
            cur = 1 - cur
            vals.append(str(cur))
            kt.append(n(e, 4))
        return (f'<g opacity="0"><animateMotion path="{path}" dur="{secs}s" repeatCount="indefinite" rotate="0"/>'
                f'<animate attributeName="opacity" values="{";".join(vals)}" keyTimes="{";".join(kt)}" '
                f'calcMode="discrete" dur="{secs}s" repeatCount="indefinite"/>'
                f'<circle r="4.5" fill="{P[colk]}" opacity="0.18"/><circle r="1.9" fill="#fff" opacity="0.95"/></g>')

    def sat_wrapped(half):
        # satélites são desenhados em coordenadas locais do anel; envolvemos cada um no grupo do anel
        out = []
        for (k, b, s) in SATELLITES:
            rx, ry, rho, colk = ORBITS[k][:4]
            inner = satellite(k, b, s, half)
            if not inner:
                continue
            if anim:
                out.append(f'<g transform="translate({CX} {CY}) rotate({rho})">{inner}</g>')
            else:
                out.append(inner)
        return "".join(out)

    add('<g id="orbits-back">')
    for k in ORBITS:
        add(ring_group(k, "back"))
    add(sat_wrapped("back"))
    add('</g>')

    # ── esfera ───────────────────────────────────────────────────────
    add(f'<g id="globe" transform="translate({CX} {CY})">')
    add(f'<circle r="{R+46}" fill="url(#atmo)"/>')
    add(f'<circle r="{R}" fill="url(#body)"/>')

    # tudo que gira / está preso ao eixo fica no grupo inclinado
    add(f'<g id="globe-tilted" transform="rotate({TILT})">')

    # eixo de rotação (segmentos curtos fora da esfera)
    add(f'<g stroke="{P["cyan"]}" stroke-width="0.8" opacity="0.32" stroke-dasharray="2 4">'
        f'<path d="M0 {-R-34}V{n(-R*math.cos(E)-2)}M0 {n(R*math.cos(E)+2)}V{R+34}"/></g>')
    add(f'<circle cx="0" cy="{-R-34}" r="1.8" fill="{P["cyan"]}" opacity="0.6"/>'
        f'<circle cx="0" cy="{R+34}" r="1.8" fill="{P["cyan"]}" opacity="0.35"/>')

    # paralelos (estáticos)
    add(f'<g id="parallels" fill="none" stroke="{P["cyan"]}" stroke-width="0.8">')
    for lat in (-60, -30, 0, 30, 60):
        phi = math.radians(lat)
        yc = -R * math.sin(phi) * math.cos(E)
        rx, ry = R * math.cos(phi), R * math.cos(phi) * math.sin(E)
        k = -math.tan(phi) * math.tan(E)
        lam0 = math.pi if k <= -1 else (0.0 if k >= 1 else math.acos(k))
        U, V = (0, ry), (rx, 0)
        fo, bo = (0.46, 0.11) if lat == 0 else (0.28, 0.07)
        if lam0 > 0.02:
            nseg = max(2, math.ceil(2 * lam0 / (math.pi / 2)))
            add(f'<path d="{bez_arc((0, yc), U, V, -lam0, lam0, nseg)}" opacity="{fo}"/>')
        if lam0 < math.pi - 0.02:
            span = 2 * math.pi - 2 * lam0
            nseg = max(2, math.ceil(span / (math.pi / 2)))
            add(f'<path d="{bez_arc((0, yc), U, V, lam0, 2 * math.pi - lam0, nseg)}" opacity="{bo}"/>')
    add('</g>')

    # meridianos (giram; o conjunto se repete a cada 30°, então o laço é curto)
    add(f'<g id="meridians" fill="none" stroke="{P["cyan"]}" stroke-width="0.8">')
    FR = 8
    for i in range(N_MERIDIANS):
        if anim:
            fd, bd, fo = [], [], []
            for k in range(FR + 1):
                L = math.radians(i * MERIDIAN_STEP + k * MERIDIAN_STEP / FR)
                f, b, c = meridian_arcs(L)
                fd.append(f); bd.append(b); fo.append(n(0.08 + 0.40 * max(0.0, c), 2))
            f0 = fd[0]; b0 = bd[0]
            add(f'<path d="{f0}" opacity="{fo[0]}">'
                f'<animate attributeName="d" values="{";".join(fd)}" dur="{n(LOOP_MERIDIAN)}s" repeatCount="indefinite"/>'
                f'<animate attributeName="opacity" values="{";".join(fo)}" dur="{n(LOOP_MERIDIAN)}s" repeatCount="indefinite"/></path>')
            add(f'<path d="{b0}" opacity="0.06">'
                f'<animate attributeName="d" values="{";".join(bd)}" dur="{n(LOOP_MERIDIAN)}s" repeatCount="indefinite"/></path>')
        else:
            L = math.radians(i * MERIDIAN_STEP + SPIN * t)
            f, b, c = meridian_arcs(L)
            add(f'<path d="{f}" opacity="{n(0.08 + 0.40 * max(0.0, c), 2)}"/><path d="{b}" opacity="0.06"/>')
    add('</g>')

    # nós e conexões na superfície (grafo = "sistema de software")
    pts = []
    tries = 0
    while len(pts) < 36 and tries < 5000:
        tries += 1
        phi = math.asin(rnd.uniform(-0.93, 0.93))
        lam = rnd.uniform(0, 2 * math.pi)
        v = (math.cos(phi) * math.sin(lam), math.sin(phi), math.cos(phi) * math.cos(lam))
        if all(math.acos(max(-1, min(1, v[0] * q[0] + v[1] * q[1] + v[2] * q[2]))) > math.radians(17)
               for _, _, q in pts):
            pts.append((phi, lam, v))
    # hubs = 6 nós bem espalhados (uma alusão sutil às 6 tecnologias)
    hubs = [0]
    while len(hubs) < 6:
        best, bd = None, -1
        for i, (_, _, v) in enumerate(pts):
            if i in hubs:
                continue
            dmin = min(math.acos(max(-1, min(1, v[0]*pts[h][2][0] + v[1]*pts[h][2][1] + v[2]*pts[h][2][2]))) for h in hubs)
            if dmin > bd:
                best, bd = i, dmin
        hubs.append(best)

    links = set()
    for i, (_, _, vi) in enumerate(pts):
        near = sorted(((math.acos(max(-1, min(1, vi[0]*vj[0] + vi[1]*vj[1] + vi[2]*vj[2]))), j)
                       for j, (_, _, vj) in enumerate(pts) if j != i))
        for dist, j in near[:2]:
            if dist < math.radians(44):
                links.add(tuple(sorted((i, j))))

    NF = 36
    add(f'<g id="links" fill="none" stroke="{P["cyan"]}" stroke-width="0.7">')
    for (i, j) in sorted(links):
        if anim:
            ds, os_ = [], []
            for k in range(NF + 1):
                th = math.radians(k * 360 / NF)
                xi, yi, zi = surf(pts[i][0], pts[i][1], th)
                xj, yj, zj = surf(pts[j][0], pts[j][1], th)
                ds.append(f"M{n(xi)} {n(yi)}L{n(xj)} {n(yj)}")
                os_.append(n(0.04 + 0.36 * min(facing(zi), facing(zj)), 2))
            add(f'<path d="{ds[0]}" opacity="{os_[0]}">'
                f'<animate attributeName="d" values="{";".join(ds)}" dur="{n(LOOP_NODES)}s" repeatCount="indefinite"/>'
                f'<animate attributeName="opacity" values="{";".join(os_)}" dur="{n(LOOP_NODES)}s" repeatCount="indefinite"/></path>')
        else:
            th = math.radians(SPIN * t)
            xi, yi, zi = surf(pts[i][0], pts[i][1], th)
            xj, yj, zj = surf(pts[j][0], pts[j][1], th)
            add(f'<path d="M{n(xi)} {n(yi)}L{n(xj)} {n(yj)}" opacity="{n(0.04 + 0.36 * min(facing(zi), facing(zj)), 2)}"/>')
    add('</g>')

    add('<g id="nodes">')
    for idx, (phi, lam, _) in enumerate(pts):
        hub = idx in hubs
        dot = (f'<circle r="3.1" fill="{P["cyan"]}"/><circle r="7.5" fill="none" stroke="{P["cyan"]}" stroke-width="0.8" opacity="0.55"/>'
               f'<circle r="6" fill="{P["cyan"]}" opacity="0.30" filter="url(#glow)"/>') if hub else \
              (f'<circle r="{2.0 if idx % 3 else 2.5}" fill="{P["violet"] if idx % 7 == 0 else P["cyan"]}"/>')
        if anim:
            tr, op = [], []
            for k in range(NF + 1):
                x, y, z = surf(phi, lam, math.radians(k * 360 / NF))
                tr.append(f"{n(x)} {n(y)}")
                op.append(n(0.10 + 0.85 * facing(z), 2))
            add(f'<g transform="translate({tr[0]})" opacity="{op[0]}"><animateTransform attributeName="transform" type="translate" values="{";".join(tr)}" dur="{n(LOOP_NODES)}s" repeatCount="indefinite"/>'
                f'<animate attributeName="opacity" values="{";".join(op)}" dur="{n(LOOP_NODES)}s" repeatCount="indefinite"/>{dot}</g>')
        else:
            x, y, z = surf(phi, lam, math.radians(SPIN * t))
            add(f'<g transform="translate({n(x)} {n(y)})" opacity="{n(0.10 + 0.85 * facing(z), 2)}">{dot}</g>')
    add('</g>')
    add('</g>')  # globe-tilted

    # sombreamento (terminador) e luz de borda
    add(f'<circle r="{R}" fill="url(#shade)"/>')
    add(f'<circle r="{R}" fill="none" stroke="url(#rim)" stroke-width="6" opacity="0.5" filter="url(#soft)"/>')
    add(f'<circle r="{R}" fill="none" stroke="url(#rim)" stroke-width="1.3"/>')

    # escala do limbo (tique-taques finos ao redor da esfera)
    tk = []
    for i in range(120):
        a = math.radians(i * 3)
        big = i % 5 == 0
        r0, r1 = R + 12, R + (19 if big else 15.5)
        tk.append(f"M{n(r0*math.cos(a))} {n(r0*math.sin(a))}L{n(r1*math.cos(a))} {n(r1*math.sin(a))}")
    add(f'<path d="{"".join(tk)}" fill="none" stroke="{P["cyan"]}" stroke-width="0.8" opacity="0.30"/>')
    add('</g>')  # globe

    # ── anéis: metade da FRENTE (sobre a esfera) ─────────────────────
    add('<g id="orbits-front">')
    for k in ORBITS:
        add(ring_group(k, "front"))
    add(sat_wrapped("front"))
    add('</g>')

    # ── tecnologias em órbita (rótulos fixos com linha de chamada) ────
    add('<g id="orbit-labels">')
    STEM = 26
    for (label, key, beta, sub, direction) in ORBIT_LABELS:
        nx_, ny_ = ring_xy(key, beta)
        c = P[ORBITS[key][3]]
        if direction == "up":
            y_a, y_b = ny_ - 10, ny_ - 10 - STEM
            sub_y = y_b - 9
            main_y = sub_y - 19
        else:
            y_a, y_b = ny_ + 10, ny_ + 10 + STEM
            main_y = y_b + 21
            sub_y = main_y + 17
        tx = nx_ + 1.2   # compensa o espaçamento de letras ao centralizar
        add(f'<g>'
            f'<path d="M{n(nx_)} {n(y_a)}V{n(y_b)}" stroke="{c}" stroke-width="0.9" opacity="0.7"/>'
            f'<circle cx="{n(nx_)}" cy="{n(ny_)}" r="9" fill="none" stroke="{c}" stroke-width="0.8" opacity="0.5"/>'
            f'<circle cx="{n(nx_)}" cy="{n(ny_)}" r="8" fill="{c}" opacity="0.22" filter="url(#glow)"/>'
            f'<circle cx="{n(nx_)}" cy="{n(ny_)}" r="3.4" fill="{c}"/>'
            f'<text class="mono" x="{n(tx)}" y="{n(main_y)}" text-anchor="middle" font-size="15" letter-spacing="2.4" fill="{P["text"]}">{label}</text>'
            f'<text class="sans" x="{n(nx_)}" y="{n(sub_y)}" text-anchor="middle" font-size="12" letter-spacing="0.6" fill="{P["muted"]}">{sub}</text>'
            f'</g>')
    add('</g>')

    # ── cabeçalho da estação ─────────────────────────────────────────
    add(f'<g class="sans" font-size="12" fill="{P["muted"]}">'
        f'<text x="52" y="66" letter-spacing="4">{STATION_LEFT}</text>'
        f'<text class="mono" x="{W-52}" y="66" text-anchor="end" letter-spacing="1.6">{STATION_RIGHT}</text></g>')

    # ── nome, cargo e ticker ─────────────────────────────────────────
    SPC = 17
    add(f'<text class="sans" x="{CX + SPC/2}" y="648" text-anchor="middle" font-size="50" font-weight="300" '
        f'letter-spacing="{SPC}" fill="{P["text"]}">{NAME}</text>')
    add(f'<g class="sans" font-size="15" letter-spacing="5">'
        f'<text x="{CX-24}" y="690" text-anchor="end" fill="{P["cyan"]}">{TITLE}</text>'
        f'<path d="M{CX} 676V695" stroke="{P["dim"]}" stroke-width="1"/>'
        f'<text x="{CX+24}" y="690" text-anchor="start" fill="{P["muted"]}">{TITLE_2}</text></g>')
    add(f'<path d="M{CX-70} 722H{CX+70}" stroke="{P["cyan"]}" stroke-width="1" opacity="0.28"/>')

    nlines = len(TICKER)
    per = TICKER_SECONDS_EACH
    total = per * nlines
    for j, line in enumerate(TICKER):
        if anim:
            a, b_ = j / nlines, (j + 1) / nlines
            fade = 0.05 / nlines * 3
            keys = [(0, 0), (a, 0), (a + fade, 1), (b_ - fade, 1), (b_, 0), (1, 0)]
            if j == 0:
                keys = [(0, 0), (fade, 1), (b_ - fade, 1), (b_, 0), (1, 0)]
            if j == nlines - 1:
                keys = [(0, 0), (a, 0), (a + fade, 1), (1 - fade, 1), (1, 0)]
            ded = []
            for kt, v in keys:
                if not ded or kt > ded[-1][0] + 1e-6:
                    ded.append((kt, v))
            anim_el = (f'<animate attributeName="opacity" values="{";".join(str(v) for _, v in ded)}" '
                       f'keyTimes="{";".join(n(k_, 4) for k_, _ in ded)}" dur="{n(total)}s" repeatCount="indefinite"/>')
            base = 1 if j == 0 else 0
            add(f'<text class="sans" x="{CX}" y="756" text-anchor="middle" font-size="15" letter-spacing="1" '
                f'fill="{P["muted"]}" opacity="{base}">{line}{anim_el}</text>')
        else:
            cur = int((t % total) // per)
            add(f'<text class="sans" x="{CX}" y="756" text-anchor="middle" font-size="15" letter-spacing="1" '
                f'fill="{P["muted"]}" opacity="{1 if j == cur else 0}">{line}</text>')

    add('</g></svg>')
    return "\n".join(o)


# ══════════════════════════════════════════════════════════════════════
# CABEÇALHOS DE SEÇÃO: placa escura + régua graduada
#   (a placa escura garante legibilidade tanto no tema claro quanto no escuro)
# ══════════════════════════════════════════════════════════════════════
def build_section(label):
    P = PALETTE
    plate_w = int(len(label) * 12.6 + 58)
    x0 = plate_w + 16
    ticks = []
    x = x0
    i = 0
    while x < 1198:
        big = i % 5 == 0
        ticks.append(f"M{x} 26V{18 if big else 22}")
        x += 12
        i += 1
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 48" width="1200" height="48" role="img" aria-label="{label.title()}">
<title>{label.title()}</title>
<style>.mono{{font-family:{MONO}}}</style>
<defs><filter id="g" x="-300%" y="-300%" width="700%" height="700%"><feGaussianBlur stdDeviation="2"/></filter></defs>
<rect x="1" y="7" width="{plate_w}" height="34" rx="6" fill="#090D15" stroke="#22304A" stroke-width="1"/>
<circle cx="22" cy="24" r="5" fill="{P['cyan']}" opacity="0.35" filter="url(#g)"/>
<circle cx="22" cy="24" r="3" fill="{P['cyan']}"/>
<text class="mono" x="40" y="29" font-size="13" letter-spacing="3.6" fill="#DCE6F2">{label}</text>
<path d="M{x0} 26H1199" stroke="#64748B" stroke-width="1" opacity="0.6"/>
<path d="{"".join(ticks)}" stroke="#64748B" stroke-width="1" opacity="0.5"/>
<circle cx="1197" cy="26" r="2" fill="{P['cyan']}" opacity="0.8"/>
</svg>'''


# ══════════════════════════════════════════════════════════════════════
# GLIFOS DAS MISSÕES
# ══════════════════════════════════════════════════════════════════════
def tile_open(w, h):
    P = PALETTE
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-hidden="true">'
            f'<style>.mono{{font-family:{MONO}}}</style>'
            f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="8" fill="#070A11" stroke="#1B2635"/>')


def build_glyph_sort():
    """Barras de um Insertion Sort em andamento: prefixo ordenado + faixa que varre os pares comparados."""
    P = PALETTE
    w, h = 240, 148
    heights = [18, 24, 31, 38, 45, 52, 60, 66, 40, 78, 28, 58, 48, 72, 36, 84]
    bw, gap, x0, base = 8, 5.2, 17, 118
    o = [tile_open(w, h)]
    sorted_n = 8
    # faixa de comparação (varre pares consecutivos, em passos discretos)
    pos = [x0 + i * (bw + gap) - 4 for i in range(len(heights) - 1)]
    band_w = 2 * bw + gap + 8
    o.append(f'<rect x="{n(pos[0])}" y="26" width="{n(band_w)}" height="{base-26+6}" rx="4" fill="{P["cyan"]}" opacity="0.10">'
             f'<animate attributeName="x" values="{";".join(n(p) for p in pos)}" dur="{len(pos)*0.6}s" calcMode="discrete" repeatCount="indefinite"/></rect>')
    for i, hh in enumerate(heights):
        x = x0 + i * (bw + gap)
        if i < sorted_n:
            fill, op = P["cyan"], 0.78
        elif i == 9:
            fill, op = P["violet"], 0.95
        else:
            fill, op = "#56667C", 0.9
        o.append(f'<rect x="{n(x)}" y="{base-hh}" width="{bw}" height="{hh}" rx="1.5" fill="{fill}" opacity="{op}"/>')
    o.append(f'<path d="M14 {base+6}H{w-14}" stroke="#2A3A52" stroke-width="1"/>')
    tk = "".join(f"M{14+i*13} {base+6}v3" for i in range(0, 17))
    o.append(f'<path d="{tk}" stroke="#2A3A52" stroke-width="1"/>')
    o.append(f'<text class="mono" x="{w-14}" y="24" text-anchor="end" font-size="11" letter-spacing="1" fill="#5B6878">O(n log n)</text>')
    o.append('</svg>')
    return "".join(o)


def build_glyph_lru():
    """HEAD ⇄ nós ⇄ TAIL (lista duplamente encadeada) + tabela hash apontando para os nós."""
    P = PALETTE
    w, h = 240, 148
    o = [tile_open(w, h)]
    y, nh, nw, gap = 50, 28, 28, 10
    x = 11
    xs = []
    labels = ["HEAD", "A", "B", "C", "D", "TAIL"]
    for i, lb in enumerate(labels):
        xs.append(x)
        x += nw + gap
    for i, (lb, x) in enumerate(zip(labels, xs)):
        cx_ = x + nw / 2
        if lb in ("HEAD", "TAIL"):
            o.append(f'<rect x="{x}" y="{y+5}" width="{nw}" height="{nh-10}" rx="5" fill="none" stroke="#3A4B63" stroke-width="1"/>')
            o.append(f'<text class="mono" x="{n(cx_)}" y="{y+nh/2+3}" text-anchor="middle" font-size="8" fill="#6B7A8D">{lb}</text>')
        else:
            first, last = lb == "A", lb == "D"
            stroke = P["cyan"] if first else (P["violet"] if last else "#3A4B63")
            dash = ' stroke-dasharray="3 3"' if last else ""
            fill = "#0E1B2B" if first else "#0A0F18"
            o.append(f'<rect x="{x}" y="{y}" width="{nw}" height="{nh}" rx="5" fill="{fill}" stroke="{stroke}" stroke-width="1.1"{dash}/>')
            o.append(f'<text class="mono" x="{n(cx_)}" y="{y+nh/2+4}" text-anchor="middle" font-size="11" fill="{P["text"]}" opacity="0.85">{lb}</text>')
    # setas duplas entre vizinhos
    for i in range(len(xs) - 1):
        xa, xb = xs[i] + nw + 1.5, xs[i + 1] - 1.5
        ym = y + nh / 2
        o.append(f'<path d="M{n(xa)} {n(ym-2.2)}H{n(xb)}M{n(xa)} {n(ym+2.2)}H{n(xb)}" stroke="#4B5C74" stroke-width="0.9"/>')
        o.append(f'<path d="M{n(xb)} {n(ym-2.2)}l-2.6 -1.6v3.2zM{n(xa)} {n(ym+2.2)}l2.6 -1.6v3.2z" fill="#4B5C74"/>')
    # marcador de evicção sobre o último nó
    xe = xs[4] + nw / 2
    o.append(f'<path d="M{n(xe-4)} {y-13}l8 8M{n(xe+4)} {y-13}l-8 8" stroke="{P["violet"]}" stroke-width="1.2" stroke-linecap="round"/>')
    # tabela hash (baixo) ligada aos nós
    by = 108
    for i in range(5):
        bx = 22 + i * 40
        o.append(f'<rect x="{bx}" y="{by}" width="22" height="16" rx="3" fill="#0A0F18" stroke="#2A3A52"/>')
        o.append(f'<circle cx="{bx+11}" cy="{by+8}" r="2" fill="#56667C"/>')
    links = [(0, 1), (1, 3), (2, 2), (3, 4), (4, 3)]
    for bi, ni in links:
        bx = 22 + bi * 40 + 11
        nx_ = xs[ni + 1] + nw / 2
        o.append(f'<path d="M{bx} {by}C{bx} {by-22} {n(nx_)} {y+nh+20} {n(nx_)} {y+nh+2}" fill="none" stroke="#3A4B63" stroke-width="0.9" stroke-dasharray="1.5 3"/>')
    o.append(f'<text class="mono" x="{w-14}" y="24" text-anchor="end" font-size="11" letter-spacing="1" fill="#5B6878">O(1)</text>')
    o.append('</svg>')
    return "".join(o)


# ══════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", type=float, default=None, help="quadro estático em t segundos (QA)")
    args = ap.parse_args()
    here = pathlib.Path(__file__).resolve().parent
    out = here.parent / "assets"
    out.mkdir(exist_ok=True)

    if args.freeze is not None:
        prev = out / "_preview"
        prev.mkdir(exist_ok=True)
        (prev / f"hero_t{int(args.freeze)}.svg").write_text(build_hero(args.freeze), encoding="utf-8")
        print("preview ->", prev)
        return

    (out / "hero-observatory.svg").write_text(build_hero(None), encoding="utf-8")
    for fname, label in SECTIONS.items():
        (out / f"{fname}.svg").write_text(build_section(label), encoding="utf-8")
    (out / "mission-search-sort.svg").write_text(build_glyph_sort(), encoding="utf-8")
    (out / "mission-lru-cache.svg").write_text(build_glyph_lru(), encoding="utf-8")
    print("ok ->", out)


if __name__ == "__main__":
    main()
