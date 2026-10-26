"""Build focused routes from the existing localized guided-demo template.

No new interactive implementation or duplicate business logic: sections are
reused verbatim, with a dedicated URL for each scenario.
"""
import html
import re

SECTIONS = (
    '<section class="guided-hero"',
    '<section class="idea"',
    '<section class="film-story"',
    '<section id="recovery"',
    '<details class="purchase-more"',
    '<section class="policies"',
)


def route(code, leaf=''):
    prefix = '/' if code == 'en' else f'/{code}/'
    return prefix + leaf


def render_pages(full_page, code, messages):
    esc = html.escape
    start, rest = full_page.split('<main>', 1)
    content, tail = rest.split('</main>', 1)
    offsets = [content.index(marker) for marker in SECTIONS]
    assert offsets == sorted(offsets), 'Unexpected guided-demo template order'
    slices = [content[offsets[i]: offsets[i + 1] if i + 1 < len(offsets) else len(content)]
              for i in range(len(SECTIONS))]
    hero, idea, film, recovery, purchase, policies = slices

    # Preserve one primary heading per page and the approved family art.
    idea = idea.replace('<h2 id="brand-title">', '<h1 id="brand-title">', 1).replace('</h2>', '</h1>', 1)
    hero = hero.replace('class="guided-hero"', 'class="guided-hero home-banner"', 1)
    hero = hero.replace('<h1 id="hero-heading"', '<div id="hero-heading"', 1).replace('</h1>', '</div>', 1)
    film = film.replace('<h2 id="film-title">', '<h1 id="film-title">', 1).replace('</h2>', '</h1>', 1)
    purchase = purchase.replace('<details class="purchase-more">', '<div class="purchase-more purchase-standalone">', 1)
    summary_start = purchase.index('<summary>')
    summary_end = purchase.index('</summary>', summary_start) + len('</summary>')
    purchase = purchase[:summary_start] + purchase[summary_end:]
    close = purchase.rfind('</details>')
    assert close > 0, 'Expected closing purchase wrapper'
    purchase = purchase[:close] + '</div>' + purchase[close + len('</details>'):]
    purchase = purchase.replace('<h2 id="demo-title">', '<h1 id="demo-title">', 1).replace('</h2>', '</h1>', 1)

    def link(leaf):
        return esc(route(code, leaf), quote=True)

    def cards(compact=False):
        entries = [
            ('recovery', 'gunter/', 'catalog.gunter', 'catalog.gunter.preview', 'catalog.gunter.open'),
            ('demo', 'purchase/', 'catalog.purchase', 'purchase.preview', 'catalog.purchase.open'),
        ]
        heading = 'h3' if compact else 'h2'
        cards_html = ''
        for anchor, leaf, key, description, action in entries:
            cards_html += (
                f'<a class="catalog-card" id="{anchor}" href="{link("demos/" + leaf)}">'
                f'<{heading} class="catalog-card-label">{esc(messages[key])}</{heading}>\n'
                f'<p class="catalog-card-copy">{esc(messages[description])}</p>\n'
                f'<span class="catalog-card-action">{esc(messages[action])} <span aria-hidden="true">→</span></span>'
                '</a>\n'
            )
        return '<div class="catalog-grid">' + cards_html + '</div>'

    brand = (
        f'<header class="site-top"><a class="site-mark" href="{link("")}">stoqnist.</a>'
        f'<a class="site-nav-link" href="{link("demos/")}">{esc(messages["catalog.link"])}'
        ' <span aria-hidden="true">→</span></a></header>'
    )
    back = f'<nav class="demo-back"><a href="{link("demos/")}">← {esc(messages["catalog.back"])}</a></nav>'
    home_cards = (
        '<section class="catalog-home" aria-labelledby="catalog-home-title">'
        f'<div class="catalog-lead"><p class="eyebrow">{esc(messages["catalog.label"])}</p>'
        f'<h2 id="catalog-home-title">{esc(messages["catalog.heading"])}</h2>'
        f'<p>{esc(messages["catalog.intro"])}</p></div>{cards(compact=True)}</section>'
    )
    catalog_cards = (
        '<section class="catalog-page" aria-labelledby="catalog-title">'
        f'<p class="eyebrow">{esc(messages["catalog.label"])}</p>'
        f'<h1 id="catalog-title">{esc(messages["catalog.heading"])}</h1>'
        f'<p class="catalog-intro">{esc(messages["catalog.intro"])}</p>{cards()}'
        f'<p class="micro">{esc(messages["catalog.disclosure"])}</p></section>'
    )

    bodies = {
        '': brand + idea + home_cards + hero + policies,
        'demos/': brand + catalog_cards + policies,
        'demos/gunter/': brand + back + film + recovery + policies,
        'demos/purchase/': brand + back + purchase + policies,
    }
    anchors = {'': 'brand-title', 'demos/': 'catalog-title',
               'demos/gunter/': 'film-title', 'demos/purchase/': 'demo-title'}
    titles = {'demos/': messages['catalog.heading'],
              'demos/gunter/': messages['catalog.gunter'],
              'demos/purchase/': messages['catalog.purchase']}
    pages = {}

    for leaf, body in bodies.items():
        page_kind = {'': 'home', 'demos/': 'catalog', 'demos/gunter/': 'gunter',
                     'demos/purchase/': 'purchase'}[leaf]
        header = start.replace('<body>', f'<body class="page-{page_kind}">', 1)
        header = re.sub(
            r'(<link rel="canonical" href=")https://stoq\.page[^"]*',
            lambda m: m[1] + 'https://stoq.page' + route(code, leaf), header)
        header = re.sub(
            r'(<link rel="alternate" hreflang=")([^"]+)(" href=")https://stoq\.page[^"]*',
            lambda m: m[1] + m[2] + m[3] + 'https://stoq.page'
                + route('en' if m[2] == 'x-default' else m[2], leaf), header)
        header = re.sub(
            r'(<a data-language-link href=")[^"]*(" lang=")([^"]+)(")',
            lambda m: m[1] + route(m[3], leaf) + m[2] + m[3] + m[4], header)
        header = header.replace('href="#brand-title"', f'href="#{anchors[leaf]}"', 1)
        if leaf:
            header = re.sub(r'<title>[^<]*</title>', '<title>' + esc(titles[leaf]) + ' · stoqnist.</title>', header, count=1)
        pages[leaf + 'index.html'] = header + '<main class="site-main">' + body + '</main>' + tail
    return pages
