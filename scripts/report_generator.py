"""
Markdown report generator
Creates formatted latest_update.md with categorized content
"""

import os
from typing import List, Dict, Any
from datetime import datetime
from collections import defaultdict


class MarkdownReportGenerator:
    """Generate markdown reports for RSS updates"""

    def __init__(self):
        self.categories = ["科技", "人文", "设计", "娱乐", "其他"]
        self.platform_emojis = {
            "bilibili": "📺",
            "xiaohongshu": "📕",
            "weibo": "📱",
            "youtube": "🎬",
            "vimeo": "🎥",
            "behance": "🎨",
            "douyin": "🎵",
            "twitter": "🐦",
        }

    def generate_update_report(self, new_items: List[Dict[str, Any]],
                               output_path: str = "latest_update.md",
                               digest: bool = False) -> str:
        """Generate latest update report.
        
        Args:
            digest: If True, show only the latest 1 item per subscription.
                    If no new items, output a single-line "无更新".
        """

        if not new_items:
            content = self._generate_empty_report()
        elif digest:
            content = self._generate_digest_report(new_items, output_dir=os.path.dirname(output_path) or ".")
        else:
            content = self._generate_full_report(new_items)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        return output_path

    def _generate_digest_report(self, new_items: List[Dict[str, Any]],
                                output_dir: str = ".") -> str:
        """Generate digest report — all accounts shown, changed ones marked 🆕.

        Output is PLAIN TEXT (no markdown links/bold) for maximum compatibility
        with platforms like Feishu, WeChat, Discord etc.
        """
        import json
        from collections import OrderedDict

        # Group by subscription_url (= per account), keep newest
        by_account = OrderedDict()
        for item in new_items:
            key = item.get("subscription_url", item.get("platform", "unknown"))
            if key not in by_account:
                by_account[key] = item

        # Load previous digest snapshot
        snapshot_path = os.path.join(output_dir, "last_digest.json")
        prev_snapshot = {}
        try:
            with open(snapshot_path, "r", encoding="utf-8") as f:
                prev_snapshot = json.load(f)  # {sub_url: item_id}
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        # Determine which accounts have new content
        changed_keys = set()
        current_snapshot = {}
        for sub_url, item in by_account.items():
            item_id = item.get("item_id", "")
            current_snapshot[sub_url] = item_id
            if item_id != prev_snapshot.get(sub_url):
                changed_keys.add(sub_url)

        # Save current snapshot for next comparison
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(current_snapshot, f, ensure_ascii=False)

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_count = len(changed_keys)

        if new_count:
            header = f"📡 RSS 更新摘要 | {now} | {new_count} 个账号有新内容"
        else:
            header = f"📡 RSS 更新摘要 | {now} | 暂无新更新"

        lines = [header, ""]

        # Show ALL accounts
        for sub_url, item in by_account.items():
            platform = item.get("platform", "").lower()
            emoji = self.platform_emojis.get(platform, "🔗")
            title = item.get("title", "Untitled")
            link = item.get("link", "")
            sub_title = item.get("subscription_title", "")
            account = sub_title if sub_title and "Subscription" not in sub_title else ""
            is_new = sub_url in changed_keys

            # Single-line: tag + emoji + account + pub_date
            tag = "🆕 " if is_new else ""
            name = account or platform.title()

            # Format pub_date if available
            pub_date_str = ""
            raw_date = item.get("pub_date", "")
            if raw_date:
                try:
                    from dateutil import parser as dateparser
                    dt = dateparser.parse(raw_date)
                    pub_date_str = dt.strftime("%m-%d %H:%M")
                except Exception:
                    # fallback: try to extract date portion
                    pub_date_str = raw_date[:10] if len(raw_date) >= 10 else ""

            date_suffix = f"  {pub_date_str}" if pub_date_str else ""
            lines.append(f"{tag}{emoji} {name}{date_suffix}")

            # Title as clickable hyperlink
            if link:
                lines.append(f"   [{title}]({link})")
            else:
                lines.append(f"   {title}")

            lines.append("")

        return "\n".join(lines)

    def _generate_empty_report(self) -> str:
        """Generate report when no new items"""
        return f"""# RSS 更新报告

**生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

**更新状态**: 无新内容

本次更新未发现新内容。

---
*Generated by Universal RSS Engine*
"""

    def _generate_full_report(self, new_items: List[Dict[str, Any]]) -> str:
        """Generate full report with categorized items"""

        # Group items by category
        categorized = defaultdict(list)
        for item in new_items:
            category = item.get("category", "其他")
            categorized[category].append(item)

        # Sort categories
        sorted_categories = []
        for cat in self.categories:
            if cat in categorized:
                sorted_categories.append(cat)

        # Generate markdown
        lines = [
            "# RSS 更新报告",
            "",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"**新增内容**: {len(new_items)} 条",
            "",
        ]

        # Table of contents
        lines.append("## 目录")
        lines.append("")
        for category in sorted_categories:
            count = len(categorized[category])
            lines.append(f"- [{category}](#{category}) ({count}条)")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Content by category
        for category in sorted_categories:
            items = categorized[category]
            lines.append(f"## {category}")
            lines.append("")
            lines.append(f"*共 {len(items)} 条新内容*")
            lines.append("")

            for item in items:
                lines.extend(self._format_item(item))
                lines.append("")

            lines.append("---")
            lines.append("")

        # Statistics
        lines.append("## 统计信息")
        lines.append("")
        lines.append("| 分类 | 数量 |")
        lines.append("|------|------|")
        for category in sorted_categories:
            lines.append(f"| {category} | {len(categorized[category])} |")
        lines.append("")

        # Platform statistics
        platform_stats = defaultdict(int)
        for item in new_items:
            platform = item.get("platform", "unknown")
            platform_stats[platform] += 1

        lines.append("### 平台分布")
        lines.append("")
        lines.append("| 平台 | 数量 |")
        lines.append("|------|------|")
        for platform, count in sorted(platform_stats.items(), key=lambda x: x[1], reverse=True):
            emoji = self.platform_emojis.get(platform, "🔗")
            lines.append(f"| {emoji} {platform.title()} | {count} |")
        lines.append("")

        lines.append("---")
        lines.append("*Generated by Universal RSS Engine*")

        return "\n".join(lines)

    def _format_item(self, item: Dict[str, Any]) -> List[str]:
        """Format a single item for markdown"""
        lines = []

        # Platform emoji
        platform = item.get("platform", "").lower()
        emoji = self.platform_emojis.get(platform, "🔗")

        # Title and link
        title = item.get("title", "Untitled")
        link = item.get("link", "")

        if link:
            lines.append(f"### {emoji} [{title}]({link})")
        else:
            lines.append(f"### {emoji} {title}")

        lines.append("")

        # Description
        description = item.get("description", "")
        if description:
            # Limit description length
            desc_preview = description[:200] + "..." if len(description) > 200 else description
            lines.append(f"> {desc_preview}")
            lines.append("")

        # Metadata
        metadata_parts = []

        # Platform
        if platform:
            metadata_parts.append(f"**平台**: {platform.title()}")

        # Date
        pub_date = item.get("pub_date", "")
        if pub_date:
            try:
                if isinstance(pub_date, str):
                    dt = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                    formatted_date = dt.strftime("%Y-%m-%d %H:%M")
                    metadata_parts.append(f"**发布时间**: {formatted_date}")
            except:
                pass

        if metadata_parts:
            lines.append(" | ".join(metadata_parts))
            lines.append("")

        return lines

    def generate_summary_report(self, db, output_path: str = "summary.md") -> str:
        """Generate overall summary report"""

        subscriptions = db.get_subscriptions()
        all_items = db.get_all_items()

        lines = [
            "# RSS 订阅总览",
            "",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]

        # Subscription statistics
        lines.append("## 订阅统计")
        lines.append("")
        lines.append(f"**总订阅数**: {len(subscriptions)}")
        lines.append(f"**总内容数**: {len(all_items)}")
        lines.append("")

        # Subscriptions by platform
        platform_subs = defaultdict(int)
        for sub in subscriptions:
            platform_subs[sub.get("platform", "unknown")] += 1

        lines.append("### 按平台分布")
        lines.append("")
        lines.append("| 平台 | 订阅数 |")
        lines.append("|------|--------|")
        for platform, count in sorted(platform_subs.items(), key=lambda x: x[1], reverse=True):
            emoji = self.platform_emojis.get(platform, "🔗")
            lines.append(f"| {emoji} {platform.title()} | {count} |")
        lines.append("")

        # Category statistics
        category_items = defaultdict(int)
        for item in all_items:
            category_items[item.get("category", "其他")] += 1

        lines.append("### 按分类分布")
        lines.append("")
        lines.append("| 分类 | 内容数 |")
        lines.append("|------|--------|")
        for category in self.categories:
            if category in category_items:
                lines.append(f"| {category} | {category_items[category]} |")
        lines.append("")

        # Subscriptions list
        lines.append("## 订阅列表")
        lines.append("")

        # Group by platform
        platform_groups = defaultdict(list)
        for sub in subscriptions:
            platform_groups[sub.get("platform", "unknown")].append(sub)

        for platform in sorted(platform_groups.keys()):
            emoji = self.platform_emojis.get(platform, "🔗")
            lines.append(f"### {emoji} {platform.title()}")
            lines.append("")

            for sub in platform_groups[platform]:
                title = sub.get("title") or sub.get("url", "")
                url = sub.get("url", "")
                last_updated = sub.get("last_updated", "从未更新")

                lines.append(f"- **{title}**")
                lines.append(f"  - URL: `{url}`")
                lines.append(f"  - 最后更新: {last_updated}")
                lines.append("")

        lines.append("---")
        lines.append("*Generated by Universal RSS Engine*")

        content = "\n".join(lines)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        return output_path
