from typing import Dict, Any, Optional, List

def get_email_analytics(
    start_datetime: str,
    end_datetime: str,
    mode: str = "org",
    quartile_pin_metric: Optional[str] = None,
    special_accounts: Optional[List[str]] = None,
    output_format: str = "json"
) -> Dict[str, Any]:
    """
    Get anonymized email analytics for the organization.

    Provides privacy-preserving email activity metrics. Users are identified
    by cryptographic hashes that rotate daily at 3:00 AM Eastern.

    Args:
        start_datetime: Start of period in ISO 8601 format (e.g., "2025-12-24T09:00:00-05:00")
        end_datetime: End of period in ISO 8601 format
        mode: Analysis mode - "org" (totals), "quartile" (grouped), "individual" (per-user)
        quartile_pin_metric: For quartile mode, pin groupings to one metric:
                            "sent", "received", "ratio", or "activity"
        special_accounts: Optional list of non-staff accounts to track separately
                         (e.g., ["support@concord.org"]). These are NOT anonymized.
        output_format: "json" (default) or "csv" (only for individual mode)

    Returns:
        Dict with:
        - status: "ok" or "error"
        - data: Analytics results based on mode
        - special_accounts: Non-anonymized stats for special accounts (if provided)

    Examples:
        # Org-wide totals for last week
        get_email_analytics(start_datetime="2025-12-17T00:00:00-05:00", 
                           end_datetime="2025-12-24T00:00:00-05:00", mode="org")

        # Quartile analysis pinned by send count
        get_email_analytics(..., mode="quartile", quartile_pin_metric="sent")

        # Individual anonymized stats
        get_email_analytics(..., mode="individual")
    """
    # Imports inside function (Letta compliance - must be fully self-contained)
    import json
    import hashlib
    import subprocess
    from datetime import datetime, timedelta, date
    import pytz

    # Configuration (inlined for Letta compliance)
    _HASH_SECRET_SALT = "cc-email-analytics-v1-2025-xK9mP2qR"
    CURRENT_STAFF = frozenset([
        "emcelroy@concord.org", "kswenson@concord.org", "scytacki@concord.org",
        "phorwitz@concord.org", "hlee@concord.org", "tlord@concord.org",
        "ddamelin@concord.org", "jraiff@concord.org", "cmcintyre@concord.org",
        "wfinzer@concord.org", "kbrown@concord.org", "lbondaryk@concord.org",
        "jchao@concord.org", "apallant@concord.org", "clore@concord.org",
        "kmiller@concord.org", "kjesseneller@concord.org", "rellis@concord.org",
        "tfristoe@concord.org", "lbuoncuore@concord.org", "dkehoe@concord.org",
        "sbrau@concord.org", "dmartin@concord.org", "lstephens@concord.org",
        "mtirenin@concord.org", "awagh@concord.org", "cdorsey@concord.org",
    ])

    try:
        # Validate mode
        if mode not in ["org", "quartile", "individual"]:
            return {
                "status": "error",
                "data": {},
                "error_message": f"Invalid mode '{mode}'. Must be 'org', 'quartile', or 'individual'."
            }

        # Validate quartile_pin_metric
        if quartile_pin_metric and quartile_pin_metric not in ["sent", "received", "ratio", "activity"]:
            return {
                "status": "error",
                "data": {},
                "error_message": f"Invalid quartile_pin_metric '{quartile_pin_metric}'. Must be 'sent', 'received', 'ratio', or 'activity'."
            }

        # Validate output_format
        if output_format not in ["json", "csv"]:
            return {
                "status": "error",
                "data": {},
                "error_message": f"Invalid output_format '{output_format}'. Must be 'json' or 'csv'."
            }

        if output_format == "csv" and mode != "individual":
            return {
                "status": "error",
                "data": {},
                "error_message": "CSV output is only available for 'individual' mode."
            }

        # Validate special accounts are not in staff list
        if special_accounts:
            staff_in_special = [a for a in special_accounts if a.lower() in CURRENT_STAFF]
            if staff_in_special:
                return {
                    "status": "error",
                    "data": {},
                    "error_message": f"Special accounts cannot include staff members: {staff_in_special}"
                }

        # Parse datetimes
        try:
            start_dt = datetime.fromisoformat(start_datetime)
            end_dt = datetime.fromisoformat(end_datetime)
        except ValueError as e:
            return {
                "status": "error",
                "data": {},
                "error_message": f"Invalid datetime format. Use ISO 8601 (e.g., '2025-12-24T09:00:00-05:00'). Error: {e}"
            }

        # Check 30-day limit
        if (end_dt - start_dt).days > 30:
            return {
                "status": "error",
                "data": {},
                "error_message": "Query period cannot exceed 30 days (API limitation)."
            }

        # Ensure minimum 5-minute interval
        if (end_dt - start_dt).total_seconds() < 300:
            return {
                "status": "error",
                "data": {},
                "error_message": "Query period must be at least 5 minutes."
            }

        # Get current hash date (changes at 3AM Eastern)
        eastern = pytz.timezone('US/Eastern')
        now_eastern = datetime.now(eastern)
        if now_eastern.hour < 3:
            hash_date = (now_eastern - timedelta(days=1)).date()
        else:
            hash_date = now_eastern.date()

        # Format times for API
        start_time = start_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z") if start_dt.tzinfo is None else start_dt.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        end_time = end_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z") if end_dt.tzinfo is None else end_dt.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        # Query Admin Reports API for Gmail activity via gws CLI
        GWS_TIMEOUT = 60

        activities = []
        next_page_token = None
        MAX_PAGES = 50
        pages_fetched = 0

        while pages_fetched < MAX_PAGES:
            _params = {
                "userKey": "all",
                "applicationName": "gmail",
                "startTime": start_time,
                "endTime": end_time,
                "maxResults": 1000,
            }
            if next_page_token:
                _params["pageToken"] = next_page_token

            _cmd = ["gws"] + "admin-reports activities list".split()
            _cmd.extend(["--params", json.dumps(_params)])
            _cmd.extend(["--format", "json"])
            _r = subprocess.run(_cmd, capture_output=True, text=True, timeout=GWS_TIMEOUT)
            if _r.returncode != 0:
                return {
                    "status": "error",
                    "data": {},
                    "error_message": f"Admin Reports API error: {_r.stderr[:500] if _r.stderr else f'gws exit {_r.returncode}'}"
                }

            _data = json.loads(_r.stdout) if _r.stdout.strip() else {}
            activities.extend(_data.get("items", []))
            next_page_token = _data.get("nextPageToken")
            pages_fetched += 1
            if not next_page_token:
                break

        # Process activities - count sent/received per user
        user_stats = {}  # email -> {"sent": 0, "received": 0}
        special_stats = {}  # email -> {"sent": 0, "received": 0}
        special_set = set(a.lower() for a in (special_accounts or []))

        for activity in activities:
            actor_email = activity.get("actor", {}).get("email", "").lower()

            for event in activity.get("events", []):
                event_name = event.get("name", "")

                # Extract mail event type from nested parameters
                # Structure: parameters[].messageValue.parameter[].intValue where name="mail_event_type"
                mail_event_type = None
                for param in event.get("parameters", []):
                    if param.get("name") == "event_info":
                        msg_value = param.get("messageValue", {})
                        for p in msg_value.get("parameter", []):
                            if p.get("name") == "mail_event_type":
                                mail_event_type = p.get("intValue")
                                break
                        break

                # Determine if sent or received (1=sent, 2=received)
                is_sent = mail_event_type == "1"
                is_received = mail_event_type == "2"

                if not (is_sent or is_received):
                    continue

                # Check if special account
                if actor_email in special_set:
                    if actor_email not in special_stats:
                        special_stats[actor_email] = {"sent": 0, "received": 0}
                    if is_sent:
                        special_stats[actor_email]["sent"] += 1
                    if is_received:
                        special_stats[actor_email]["received"] += 1
                    continue

                # Check if current staff
                if actor_email not in CURRENT_STAFF:
                    continue

                # Track stats
                if actor_email not in user_stats:
                    user_stats[actor_email] = {"sent": 0, "received": 0}

                if is_sent:
                    user_stats[actor_email]["sent"] += 1
                if is_received:
                    user_stats[actor_email]["received"] += 1

        # Calculate derived metrics for each user (inlined for Letta compliance)
        user_metrics = []
        for email, stats in user_stats.items():
            sent = stats["sent"]
            received = stats["received"]
            # Inline ratio calculation
            ratio = 9999999999.0 if received == 0 else round(sent / received, 4)
            # Inline hash calculation
            hash_data = f"{email.lower()}:{hash_date}:{_HASH_SECRET_SALT}"
            user_hash = hashlib.sha256(hash_data.encode()).hexdigest()[:8]
            user_metrics.append({
                "email": email,
                "hash": user_hash,
                "sent": sent,
                "received": received,
                "ratio": ratio,
                "activity": sent + received,
            })

        # Build response based on mode
        result = {
            "status": "ok",
            "data": {
                "period": {
                    "start": start_datetime,
                    "end": end_datetime,
                },
                "hash_date": str(hash_date),
                "truncated": pages_fetched >= MAX_PAGES,
            }
        }

        if mode == "org":
            # Aggregate totals
            total_sent = sum(u["sent"] for u in user_metrics)
            total_received = sum(u["received"] for u in user_metrics)
            org_ratio = 9999999999.0 if total_received == 0 else round(total_sent / total_received, 4)
            result["data"]["org_totals"] = {
                "sent": total_sent,
                "received": total_received,
                "ratio": org_ratio,
                "activity": total_sent + total_received,
            }
            result["data"]["user_count"] = len(user_metrics)

        elif mode == "quartile":
            # Quartile analysis (inlined for Letta compliance - no nested functions)
            n = len(user_metrics)
            if n == 0:
                result["data"]["quartiles"] = {}
                result["data"]["user_count"] = 0
            else:
                metrics_list = ["sent", "received", "ratio", "activity"]

                # Calculate quartile boundaries
                q_size = n // 4
                remainder = n % 4
                q_boundaries = []
                start_idx = 0
                for i in range(4):
                    size = q_size + (1 if i < remainder else 0)
                    q_boundaries.append((start_idx, start_idx + size))
                    start_idx += size

                if quartile_pin_metric:
                    # Pinned mode - one grouping, all metrics
                    sorted_users = sorted(
                        user_metrics,
                        key=lambda x: (-x[quartile_pin_metric], x["hash"])
                    )

                    result["data"]["pinned_by"] = quartile_pin_metric
                    result["data"]["quartiles"] = {}

                    for i, (start, end) in enumerate(q_boundaries):
                        q_name = f"Q{i+1}"
                        q_users = sorted_users[start:end]
                        n_users = len(q_users)

                        q_stats = {"user_count": n_users}
                        for m in metrics_list:
                            if n_users == 0:
                                if m == "ratio":
                                    q_stats[m] = {"avg": 0}
                                else:
                                    q_stats[m] = {"count": 0, "avg": 0}
                            else:
                                values = [u[m] for u in q_users]
                                total = sum(values)
                                avg = round(total / n_users, 2)
                                if m == "ratio":
                                    q_stats[m] = {"avg": avg}
                                else:
                                    q_stats[m] = {"count": total, "avg": avg}

                        result["data"]["quartiles"][q_name] = q_stats
                else:
                    # Default mode - each metric has its own grouping
                    result["data"]["quartiles"] = {}

                    for metric in metrics_list:
                        sorted_users = sorted(
                            user_metrics,
                            key=lambda x: (-x[metric], x["hash"])
                        )

                        result["data"]["quartiles"][f"by_{metric}"] = {}

                        for i, (start, end) in enumerate(q_boundaries):
                            q_name = f"Q{i+1}"
                            q_users = sorted_users[start:end]
                            n_users = len(q_users)

                            if n_users == 0:
                                if metric == "ratio":
                                    result["data"]["quartiles"][f"by_{metric}"][q_name] = {"user_count": 0, "avg": 0}
                                else:
                                    result["data"]["quartiles"][f"by_{metric}"][q_name] = {"user_count": 0, "count": 0, "avg": 0}
                            else:
                                values = [u[metric] for u in q_users]
                                total = sum(values)
                                avg = round(total / n_users, 2)
                                if metric == "ratio":
                                    result["data"]["quartiles"][f"by_{metric}"][q_name] = {"user_count": n_users, "avg": avg}
                                else:
                                    result["data"]["quartiles"][f"by_{metric}"][q_name] = {"user_count": n_users, "count": total, "avg": avg}

                result["data"]["user_count"] = n

        elif mode == "individual":
            # Individual anonymized stats
            # Sort by hash for consistent ordering
            sorted_users = sorted(user_metrics, key=lambda x: x["hash"])

            if output_format == "csv":
                # Build CSV string
                csv_lines = ["hash,sent,received,ratio,activity"]
                for u in sorted_users:
                    csv_lines.append(f"{u['hash']},{u['sent']},{u['received']},{u['ratio']},{u['activity']}")
                result["data"]["csv"] = "\n".join(csv_lines)
            else:
                # JSON format - remove email, keep only hash
                result["data"]["users"] = [
                    {
                        "hash": u["hash"],
                        "sent": u["sent"],
                        "received": u["received"],
                        "ratio": u["ratio"],
                        "activity": u["activity"],
                    }
                    for u in sorted_users
                ]

            result["data"]["user_count"] = len(sorted_users)

        # Add special accounts if provided
        if special_accounts:
            result["special_accounts"] = [
                {
                    "account": account,
                    "sent": special_stats.get(account.lower(), {}).get("sent", 0),
                    "received": special_stats.get(account.lower(), {}).get("received", 0),
                }
                for account in special_accounts
            ]

        return result

    except Exception as e:
        import traceback
        return {
            "status": "error",
            "data": {},
            "error_message": f"Error in email analytics: {str(e)}\n{traceback.format_exc()}"
        }
