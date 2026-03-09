from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from .scoring import get_top_curators
from .monitor import get_discoveries


async def generate_digest(session: AsyncSession, since_days: int = 7) -> str:
    """Generate a Markdown weekly digest with both GitHub and Twitter sections."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=since_days)

    lines = [
        f"# Curator Radar — Weekly Digest",
        f"**Period:** {start.strftime('%b %d')} — {now.strftime('%b %d, %Y')}",
        "",
    ]

    # GitHub curators section
    gh_curators = await get_top_curators(session, top_k=10, platform="github")
    if gh_curators:
        lines.append("## GitHub Curators")
        lines.append("| Rank | User | Overlap | Earlyness | Score |")
        lines.append("|------|------|---------|-----------|-------|")
        for i, c in enumerate(gh_curators, 1):
            lines.append(
                f"| {i} | [{c['user_login']}]({c['profile_url']}) | "
                f"{c['overlap_count']} repos | {c['earlyness_mean']:.2f} | {c['overlap_score']:.1f} |"
            )
        lines.append("")

    # GitHub discoveries section
    discoveries = await get_discoveries(session, since_days)
    if discoveries:
        lines.append(f"## GitHub Discoveries ({len(discoveries)} repos)")
        lines.append("")
        for d in discoveries[:20]:
            curator_list = ", ".join(d["curators"][:5])
            lines.append(f"- **[{d['repo']}]({d['github_url']})** — {d['curator_count']} curator(s): {curator_list}")
        lines.append("")

    # Twitter curators section
    tw_curators = await get_top_curators(session, top_k=10, platform="twitter")
    if tw_curators:
        lines.append("## Twitter Curators")
        lines.append("| Rank | Handle | Overlap | Score |")
        lines.append("|------|--------|---------|-------|")
        for i, c in enumerate(tw_curators, 1):
            lines.append(
                f"| {i} | [@{c['user_login']}]({c['profile_url']}) | "
                f"{c['overlap_count']} tweets | {c['overlap_score']:.1f} |"
            )
        lines.append("")

    if not gh_curators and not tw_curators:
        lines.append("No curator data yet. Run backfill first.")
        lines.append("")

    return "\n".join(lines)
