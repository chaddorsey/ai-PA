from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from .scoring import get_top_curators
from .monitor import get_discoveries


async def generate_digest(session: AsyncSession, since_days: int = 7) -> str:
    """Generate a Markdown weekly digest."""
    curators = await get_top_curators(session, top_k=10)
    discoveries = await get_discoveries(session, since_days)

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=since_days)

    lines = [
        f"# Curator Radar — Weekly Digest",
        f"**Period:** {start.strftime('%b %d')} — {now.strftime('%b %d, %Y')}",
        "",
    ]

    # Top curators section
    lines.append("## Top Curators")
    lines.append("| Rank | User | Overlap | Earlyness | Score |")
    lines.append("|------|------|---------|-----------|-------|")
    for i, c in enumerate(curators, 1):
        lines.append(
            f"| {i} | [{c['user_login']}]({c['github_url']}) | "
            f"{c['overlap_count']} repos | {c['earlyness_mean']:.2f} | {c['overlap_score']:.1f} |"
        )
    lines.append("")

    # Discoveries section
    if discoveries:
        lines.append(f"## New Discoveries ({len(discoveries)} repos)")
        lines.append("")
        for d in discoveries[:20]:
            curator_list = ", ".join(d["curators"][:5])
            lines.append(f"- **[{d['repo']}]({d['github_url']})** — {d['curator_count']} curator(s): {curator_list}")
        lines.append("")
    else:
        lines.append("## New Discoveries")
        lines.append("No new discoveries this period.")
        lines.append("")

    return "\n".join(lines)
