"""Business OS v3.0 — Admin Portal service.

A lightweight server-rendered UI for the Business Registry.
No React/build step yet. This keeps deployment simple on Render.
"""

from __future__ import annotations

from html import escape
from typing import Any

from database import SessionLocal
from business_registry.models import BusinessEvent, MasterProduct, ProductChannel
from business_os.executive.genome.models import ProductGenome


class AdminPortalService:
    version = "business-os-ui-3.0"

    @classmethod
    def home(cls) -> str:
        db = SessionLocal()
        try:
            total_products = db.query(MasterProduct).count()
            active_products = db.query(MasterProduct).filter(MasterProduct.active == True).count()
            channel_rows = db.query(ProductChannel).count()
            mapped_channels = (
                db.query(ProductChannel)
                .filter(
                    (ProductChannel.status == "Mapped")
                    | (ProductChannel.asin.isnot(None))
                    | (ProductChannel.channel_product_id.isnot(None))
                    | (ProductChannel.channel_listing_id.isnot(None))
                )
                .count()
            )
            genomes = db.query(ProductGenome).count()
            events = db.query(BusinessEvent).count()

            cards = [
                ("Master Products", total_products, "/business-os/ui/products", "Canonical product records"),
                ("Active Products", active_products, "/business-os/ui/products?active=true", "Currently active products"),
                ("Channel Rows", channel_rows, "/business-os/ui/channels", "Amazon / Shopify / Etsy mappings"),
                ("Mapped Channels", mapped_channels, "/business-os/ui/channels?mapped=true", "Rows with identifiers"),
                ("Product Genomes", genomes, "/business-os/ui/genomes", "Executive product profiles"),
                ("Business Events", events, "/business-os/ui/events", "Registry timeline"),
            ]

            body = f"""
            <section class="hero">
              <div>
                <p class="eyebrow">Business OS v3.0</p>
                <h1>Admin Portal</h1>
                <p class="muted">Manage the Business Registry, inspect product mappings, and review executive product intelligence.</p>
              </div>
              <div class="actions">
                <a class="button primary" href="/business-os/ui/products">Open Products</a>
                <a class="button" href="/docs">Swagger</a>
              </div>
            </section>

            <section class="grid">
              {''.join(cls._card(title, value, href, subtitle) for title, value, href, subtitle in cards)}
            </section>

            <section class="panel">
              <h2>What to do next</h2>
              <ol>
                <li>Open <strong>Products</strong> and search for your Amazon products.</li>
                <li>Open a product and confirm the Amazon channel mappings.</li>
                <li>Use Swagger Registry Manager endpoints to edit mappings until the GUI editor is added.</li>
                <li>Recalculate Product Genomes after mappings improve.</li>
              </ol>
            </section>
            """
            return cls._layout("Business OS Admin Portal", body)
        finally:
            db.close()

    @classmethod
    def products(cls, q: str | None = None, active: bool | None = None, limit: int = 100) -> str:
        db = SessionLocal()
        try:
            query = db.query(MasterProduct)
            if q:
                like = f"%{q}%"
                query = query.filter(
                    (MasterProduct.name.ilike(like))
                    | (MasterProduct.primary_sku.ilike(like))
                    | (MasterProduct.master_product_id.ilike(like))
                    | (MasterProduct.brand.ilike(like))
                    | (MasterProduct.product_family.ilike(like))
                )
            if active is not None:
                query = query.filter(MasterProduct.active == active)

            rows = query.order_by(MasterProduct.master_product_id.asc()).limit(max(1, min(limit, 500))).all()

            body = f"""
            <section class="page-header">
              <div>
                <p class="eyebrow">Registry</p>
                <h1>Products</h1>
                <p class="muted">{len(rows)} products shown.</p>
              </div>
              <a class="button" href="/business-os/ui">Back</a>
            </section>

            <form class="search" method="get" action="/business-os/ui/products">
              <input name="q" placeholder="Search by product, SKU, brand, family..." value="{escape(q or '')}" />
              <select name="active">
                <option value="">All</option>
                <option value="true" {'selected' if active is True else ''}>Active</option>
                <option value="false" {'selected' if active is False else ''}>Archived</option>
              </select>
              <button class="button primary" type="submit">Search</button>
            </form>

            <section class="panel table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Product</th>
                    <th>Brand</th>
                    <th>Family</th>
                    <th>SKU</th>
                    <th>Status</th>
                    <th>Active</th>
                  </tr>
                </thead>
                <tbody>
                  {''.join(cls._product_row(row) for row in rows)}
                </tbody>
              </table>
            </section>
            """
            return cls._layout("Products · Business OS", body)
        finally:
            db.close()

    @classmethod
    def product_detail(cls, master_product_id: str) -> str:
        db = SessionLocal()
        try:
            product = db.query(MasterProduct).filter(MasterProduct.master_product_id == master_product_id).first()
            if not product:
                return cls._layout("Product not found", f"""
                <section class="panel"><h1>Product not found</h1><p>{escape(master_product_id)}</p><a class="button" href="/business-os/ui/products">Back to products</a></section>
                """)

            channels = (
                db.query(ProductChannel)
                .filter(ProductChannel.master_product_id == master_product_id)
                .order_by(ProductChannel.channel.asc())
                .all()
            )
            genome = db.query(ProductGenome).filter(ProductGenome.master_product_id == master_product_id).first()
            events = (
                db.query(BusinessEvent)
                .filter(BusinessEvent.master_product_id == master_product_id)
                .order_by(BusinessEvent.occurred_at.desc())
                .limit(20)
                .all()
            )

            genome_html = cls._genome_panel(genome)
            channels_html = ''.join(cls._channel_row(row) for row in channels)
            events_html = ''.join(cls._event_item(row) for row in events) or '<p class="muted">No events yet.</p>'

            body = f"""
            <section class="page-header">
              <div>
                <p class="eyebrow">{escape(product.master_product_id)}</p>
                <h1>{escape(product.name or '')}</h1>
                <p class="muted">{escape(product.brand or 'No brand')} · {escape(product.product_family or 'No family')} · SKU {escape(product.primary_sku or '—')}</p>
              </div>
              <a class="button" href="/business-os/ui/products">Back</a>
            </section>

            <section class="grid two">
              <div class="panel">
                <h2>Registry</h2>
                {cls._kv('Master Product ID', product.master_product_id)}
                {cls._kv('Brand', product.brand)}
                {cls._kv('Family', product.product_family)}
                {cls._kv('Primary SKU', product.primary_sku)}
                {cls._kv('EAN/UPC', product.ean_upc)}
                {cls._kv('Status', product.status)}
                {cls._kv('Lifecycle', product.lifecycle_stage)}
                {cls._kv('Active', str(product.active))}
                <p class="muted">{escape(product.notes or '')}</p>
              </div>

              {genome_html}
            </section>

            <section class="panel table-wrap">
              <h2>Channel Mappings</h2>
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Channel</th>
                    <th>Marketplace</th>
                    <th>SKU</th>
                    <th>ASIN</th>
                    <th>Channel Product ID</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>{channels_html}</tbody>
              </table>
              <p class="muted">Use Swagger Registry Manager endpoints to edit mappings for now. GUI editing comes next.</p>
            </section>

            <section class="panel">
              <h2>Recent Events</h2>
              <div class="timeline">{events_html}</div>
            </section>
            """
            return cls._layout(f"{product.name} · Business OS", body)
        finally:
            db.close()

    @classmethod
    def channels(cls, mapped: bool | None = None, limit: int = 250) -> str:
        db = SessionLocal()
        try:
            query = db.query(ProductChannel)
            if mapped is True:
                query = query.filter(
                    (ProductChannel.status == "Mapped")
                    | (ProductChannel.asin.isnot(None))
                    | (ProductChannel.channel_product_id.isnot(None))
                    | (ProductChannel.channel_listing_id.isnot(None))
                )
            elif mapped is False:
                query = query.filter(
                    (ProductChannel.status != "Mapped")
                    & (ProductChannel.asin.is_(None))
                    & (ProductChannel.channel_product_id.is_(None))
                    & (ProductChannel.channel_listing_id.is_(None))
                )

            rows = query.order_by(ProductChannel.master_product_id.asc(), ProductChannel.channel.asc()).limit(max(1, min(limit, 1000))).all()
            body = f"""
            <section class="page-header">
              <div>
                <p class="eyebrow">Registry</p>
                <h1>Channel Mappings</h1>
                <p class="muted">{len(rows)} rows shown.</p>
              </div>
              <a class="button" href="/business-os/ui">Back</a>
            </section>

            <section class="panel table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Master Product</th>
                    <th>Channel</th>
                    <th>Marketplace</th>
                    <th>SKU</th>
                    <th>ASIN</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>{''.join(cls._channel_row(row, include_product=True) for row in rows)}</tbody>
              </table>
            </section>
            """
            return cls._layout("Channels · Business OS", body)
        finally:
            db.close()

    @classmethod
    def genomes(cls, limit: int = 100) -> str:
        db = SessionLocal()
        try:
            rows = db.query(ProductGenome).order_by(ProductGenome.product_health.desc()).limit(max(1, min(limit, 500))).all()
            body = f"""
            <section class="page-header">
              <div>
                <p class="eyebrow">Executive Brain</p>
                <h1>Product Genomes</h1>
                <p class="muted">{len(rows)} profiles shown.</p>
              </div>
              <a class="button" href="/business-os/ui">Back</a>
            </section>

            <section class="panel table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Product</th>
                    <th>Health</th>
                    <th>Organic</th>
                    <th>ADI</th>
                    <th>Confidence</th>
                    <th>Archetype</th>
                  </tr>
                </thead>
                <tbody>{''.join(cls._genome_row(row) for row in rows)}</tbody>
              </table>
            </section>
            """
            return cls._layout("Genomes · Business OS", body)
        finally:
            db.close()

    @classmethod
    def events(cls, limit: int = 100) -> str:
        db = SessionLocal()
        try:
            rows = db.query(BusinessEvent).order_by(BusinessEvent.occurred_at.desc()).limit(max(1, min(limit, 500))).all()
            body = f"""
            <section class="page-header">
              <div>
                <p class="eyebrow">Timeline</p>
                <h1>Business Events</h1>
                <p class="muted">{len(rows)} recent events.</p>
              </div>
              <a class="button" href="/business-os/ui">Back</a>
            </section>

            <section class="panel timeline">
              {''.join(cls._event_item(row) for row in rows)}
            </section>
            """
            return cls._layout("Events · Business OS", body)
        finally:
            db.close()

    @staticmethod
    def _layout(title: str, body: str) -> str:
        return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>{escape(title)}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root {{
      --bg: #0f172a;
      --panel: #111827;
      --panel2: #1f2937;
      --text: #f8fafc;
      --muted: #94a3b8;
      --line: rgba(255,255,255,.10);
      --brand: #d4af37;
      --brand2: #e9dcc2;
      --good: #22c55e;
      --warn: #f59e0b;
      --bad: #ef4444;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: radial-gradient(circle at top left, rgba(212,175,55,.18), transparent 32rem), var(--bg);
      color: var(--text);
    }}
    a {{ color: inherit; }}
    .shell {{ max-width: 1200px; margin: 0 auto; padding: 28px; }}
    .nav {{ display:flex; justify-content:space-between; align-items:center; margin-bottom: 28px; }}
    .brand {{ font-weight: 800; letter-spacing: -.03em; }}
    .nav a {{ text-decoration:none; color:var(--muted); margin-left:18px; font-size:14px; }}
    .hero, .page-header {{ display:flex; justify-content:space-between; gap:24px; align-items:flex-start; margin-bottom:24px; }}
    h1 {{ font-size: 44px; line-height: 1.05; margin: 0 0 10px; letter-spacing: -.05em; }}
    h2 {{ margin: 0 0 16px; }}
    .eyebrow {{ color: var(--brand); text-transform: uppercase; font-weight: 800; letter-spacing:.12em; font-size:12px; margin:0 0 8px; }}
    .muted {{ color: var(--muted); }}
    .grid {{ display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:16px; margin: 18px 0; }}
    .grid.two {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .card, .panel {{
      background: linear-gradient(180deg, rgba(255,255,255,.055), rgba(255,255,255,.025));
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 20px;
      box-shadow: 0 20px 50px rgba(0,0,0,.20);
    }}
    .card {{ text-decoration:none; display:block; }}
    .card .value {{ font-size: 34px; font-weight: 900; margin: 8px 0; }}
    .actions {{ display:flex; gap:10px; }}
    .button, button {{
      display:inline-flex; align-items:center; justify-content:center;
      border:1px solid var(--line); background:var(--panel2); color:var(--text);
      padding: 10px 14px; border-radius: 12px; text-decoration:none; font-weight:700;
      cursor:pointer;
    }}
    .button.primary, button.primary {{ background: var(--brand); color:#111827; border-color: transparent; }}
    .search {{ display:flex; gap:10px; margin: 0 0 18px; }}
    input, select {{
      background: var(--panel); color: var(--text); border:1px solid var(--line);
      padding: 11px 12px; border-radius: 12px; min-width: 220px;
    }}
    .search input {{ flex:1; }}
    .table-wrap {{ overflow-x:auto; }}
    table {{ width:100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 12px 10px; text-align:left; vertical-align: top; }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing:.08em; }}
    tr:hover td {{ background: rgba(255,255,255,.025); }}
    .pill {{ display:inline-flex; padding:4px 8px; border-radius:999px; background:rgba(255,255,255,.08); font-size:12px; color:var(--muted); }}
    .score {{ font-weight:900; }}
    .kv {{ display:flex; justify-content:space-between; gap:12px; border-bottom:1px solid var(--line); padding:10px 0; }}
    .kv span:first-child {{ color:var(--muted); }}
    .bar {{ background: rgba(255,255,255,.08); border-radius: 999px; height: 9px; overflow: hidden; margin-top: 5px; }}
    .fill {{ height: 100%; background: var(--brand); }}
    .timeline-item {{ border-left: 2px solid var(--brand); padding: 0 0 18px 14px; margin-left: 6px; }}
    .timeline-item h3 {{ margin: 0 0 4px; font-size: 15px; }}
    @media (max-width: 800px) {{
      .grid, .grid.two {{ grid-template-columns: 1fr; }}
      .hero, .page-header, .nav {{ flex-direction:column; }}
      h1 {{ font-size: 34px; }}
      .search {{ flex-direction:column; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <nav class="nav">
      <a class="brand" href="/business-os/ui">Business OS</a>
      <div>
        <a href="/business-os/ui/products">Products</a>
        <a href="/business-os/ui/channels">Channels</a>
        <a href="/business-os/ui/genomes">Genomes</a>
        <a href="/business-os/ui/events">Events</a>
        <a href="/docs">Swagger</a>
      </div>
    </nav>
    {body}
  </main>
</body>
</html>"""

    @staticmethod
    def _card(title: str, value: Any, href: str, subtitle: str) -> str:
        return f"""
        <a class="card" href="{escape(href)}">
          <div class="muted">{escape(title)}</div>
          <div class="value">{escape(str(value))}</div>
          <div class="muted">{escape(subtitle)}</div>
        </a>
        """

    @staticmethod
    def _product_row(row: MasterProduct) -> str:
        return f"""
        <tr>
          <td><a href="/business-os/ui/products/{escape(row.master_product_id)}">{escape(row.master_product_id)}</a></td>
          <td>{escape(row.name or '')}</td>
          <td>{escape(row.brand or '—')}</td>
          <td>{escape(row.product_family or '—')}</td>
          <td>{escape(row.primary_sku or '—')}</td>
          <td><span class="pill">{escape(row.status or '—')}</span></td>
          <td>{'Yes' if row.active else 'No'}</td>
        </tr>
        """

    @staticmethod
    def _channel_row(row: ProductChannel, include_product: bool = False) -> str:
        first = f'<td><a href="/business-os/ui/products/{escape(row.master_product_id)}">{escape(row.master_product_id)}</a></td>' if include_product else f"<td>{row.id}</td>"
        if include_product:
            row_id = f"<td>{row.id}</td>"
            cells = row_id + first
        else:
            cells = first
        return f"""
        <tr>
          {cells}
          <td>{escape(row.channel or '—')}</td>
          <td>{escape(row.marketplace or '—')}</td>
          <td>{escape(row.sku or '—')}</td>
          <td>{escape(row.asin or '—')}</td>
          <td>{escape(row.channel_product_id or '—')}</td>
          <td><span class="pill">{escape(row.status or '—')}</span></td>
        </tr>
        """

    @staticmethod
    def _genome_row(row: ProductGenome) -> str:
        return f"""
        <tr>
          <td><a href="/business-os/ui/products/{escape(row.master_product_id)}">{escape(row.name or row.master_product_id)}</a></td>
          <td class="score">{row.product_health}</td>
          <td>{row.organic_strength}</td>
          <td>{row.advertising_dependency_index}</td>
          <td>{row.confidence}</td>
          <td><span class="pill">{escape(row.archetype or '—')}</span></td>
        </tr>
        """

    @staticmethod
    def _event_item(row: BusinessEvent) -> str:
        when = row.occurred_at.isoformat() if row.occurred_at else ""
        return f"""
        <div class="timeline-item">
          <h3>{escape(row.title or row.event_type or '')}</h3>
          <div class="muted">{escape(row.event_type or '')} · {escape(when)}</div>
          <p>{escape(row.description or '')}</p>
        </div>
        """

    @classmethod
    def _genome_panel(cls, row: ProductGenome | None) -> str:
        if not row:
            return """
            <div class="panel">
              <h2>Product Genome</h2>
              <p class="muted">No Product Genome calculated yet.</p>
            </div>
            """
        return f"""
        <div class="panel">
          <h2>Product Genome</h2>
          {cls._score_bar('Health', row.product_health)}
          {cls._score_bar('Organic Strength', row.organic_strength)}
          {cls._score_bar('Advertising Dependency', row.advertising_dependency_index)}
          {cls._score_bar('Profitability', row.profitability)}
          {cls._kv('Archetype', row.archetype)}
          {cls._kv('Lifecycle', row.lifecycle_stage)}
          {cls._kv('Objective', row.objective)}
          <p class="muted">{escape(row.summary or '')}</p>
        </div>
        """

    @staticmethod
    def _score_bar(label: str, value: int | None) -> str:
        safe = max(0, min(100, int(value or 0)))
        return f"""
        <div style="margin-bottom:14px">
          <div class="kv"><span>{escape(label)}</span><strong>{safe}</strong></div>
          <div class="bar"><div class="fill" style="width:{safe}%"></div></div>
        </div>
        """

    @staticmethod
    def _kv(label: str, value: Any) -> str:
        return f'<div class="kv"><span>{escape(label)}</span><strong>{escape(str(value) if value is not None else "—")}</strong></div>'
