import base64
import random
import json
import re
from urllib.parse import quote, unquote
from v2share import V2Data
from src.db import Subscription, Node
from src.utils.cache import LINKS
from src.utils.key import gen_uuid, gen_password


class LinkGeneration:
    @classmethod
    def _extract_emoji(cls, text: str) -> str:
        if not text:
            return ""
        match = re.search(
            r"[\U0001F1E6-\U0001F1FF\U0001F300-\U0001F5FF\U0001F600-\U0001F64F"
            r"\U0001F680-\U0001F6FF\U0001F700-\U0001F77F\U0001F780-\U0001F7FF"
            r"\U0001F800-\U0001F8FF\U0001F900-\U0001F9FF\U0001FA00-\U0001FAFF"
            r"\U00002700-\U000027BF\U00002600-\U000026FF]+",
            text,
        )
        return match.group(0) if match else ""

    @classmethod
    def _get_link_remark(cls, link: str) -> str:
        if link.startswith("vmess://"):
            try:
                decoded = base64.b64decode(link[8:]).decode("utf-8")
                config = json.loads(decoded)
                return str(config.get("ps", "") or "")
            except Exception:
                return ""
        if "#" in link:
            return unquote(link.split("#", 1)[1])
        return ""

    @classmethod
    def _format_link_remark(cls, sub: Subscription, node: Node, original_remark: str) -> str:
        if not sub.owner or not sub.owner.config_rename or sub.owner.config_rename.strip() == "":
            return original_remark

        emoji = cls._extract_emoji(original_remark)
        server_name = original_remark.replace(emoji, "", 1).strip() if emoji else original_remark
        config_rename = sub.owner.config_rename

        format_vars = sub.format.copy()
        format_vars["server_id"] = str(node.id).zfill(2)
        format_vars["server_emoji"] = emoji
        format_vars["server_name"] = server_name
        format_vars["server_usage"] = node.usage_rate or "1.0"

        formatted = config_rename.format(**format_vars)
        return re.sub(r"\s{2,}", " ", formatted).strip()

    @classmethod
    def _replace_hash_remark(cls, link: str, new_remark: str) -> str:
        base = link.split("#", 1)[0]
        return f"{base}#{quote(new_remark)}"

    @classmethod
    async def _generate_placeholder_links(cls, sub: Subscription) -> list[str]:
        links = []
        for place in sub.placeholders:
            v2data = V2Data(
                protocol="vless",
                remark=place["remark"].format(**sub.format),
                address=place.get("address", Subscription.generate_server_key()).format(**sub.format),
                port=place.get("port", 1),
                uuid=place.get("uuid", Subscription.generate_access_key()).format(**sub.format),
            )
            links.append(v2data.to_link())
        return links

    @classmethod
    def _replace_link_credentials(cls, link: str, sub: Subscription, node: Node) -> str | None:
        original_remark = cls._get_link_remark(link)
        new_remark = cls._format_link_remark(sub, node, original_remark)
        if link.startswith("vless://"):
            parts = link[8:].split("@", 1)
            if len(parts) == 2:
                new_uuid = gen_uuid(sub.access_key)
                updated = f"vless://{new_uuid}@{parts[1]}"
                return cls._replace_hash_remark(updated, new_remark)

        elif link.startswith("vmess://"):
            try:
                decoded = base64.b64decode(link[8:]).decode("utf-8")
                config = json.loads(decoded)
                config["id"] = gen_uuid(sub.access_key)
                config["ps"] = new_remark
                encoded = base64.b64encode(json.dumps(config).encode()).decode()
                return f"vmess://{encoded}"
            except Exception:
                return None

        elif link.startswith("trojan://"):
            parts = link[9:].split("@", 1)
            if len(parts) == 2:
                new_password = gen_password(sub.access_key)
                updated = f"trojan://{new_password}@{parts[1]}"
                return cls._replace_hash_remark(updated, new_remark)

        elif link.startswith("ss://"):
            try:
                at_index = link.index("@")
                before_at = link[5:at_index]
                after_at = link[at_index:]

                decoded = base64.b64decode(before_at).decode("utf-8")
                if ":" in decoded:
                    method = decoded.split(":", 1)[0]
                    new_password = gen_password(sub.access_key)
                    new_credentials = f"{method}:{new_password}"
                    encoded = base64.b64encode(new_credentials.encode()).decode()
                    updated = f"ss://{encoded}{after_at}"
                    return cls._replace_hash_remark(updated, new_remark)
            except Exception:
                return None
        return None

    @classmethod
    def _get_node_links(cls, sub: Subscription, node: Node) -> list[str]:
        """Get and process links for a specific node"""
        if node.id not in LINKS or not LINKS[node.id]:
            return []

        node_links = []
        for cached_link in LINKS[node.id]:
            modified_link = cls._replace_link_credentials(cached_link, sub, node)
            if modified_link:
                node_links.append(modified_link)

        return node_links

    @classmethod
    async def generate(cls, sub: Subscription) -> list[str, None]:
        placeholder_links = await cls._generate_placeholder_links(sub)
        links = []

        if sub.is_active:
            sorted_nodes = sorted(sub.nodes, key=lambda n: n.priority, reverse=True)

            active_nodes = [node for node in sorted_nodes if node.availabled and node.show_configs]

            node_links_map: dict[Node, list[str]] = {}
            for node in active_nodes:
                node_links = cls._get_node_links(sub, node)
                node_links = node_links[node.offset_link :]
                random.shuffle(node_links)
                node_links_map[node] = node_links

            link_count = 0
            max_links = sub.owner.max_links if sub.owner.max_links and sub.owner.max_links > 0 else None

            while any(node_links_map.values()):
                for node in list(node_links_map.keys()):
                    node_links = node_links_map[node]

                    if not node_links:
                        continue

                    if max_links and link_count >= max_links:
                        break

                    batch_size = node.batch_size
                    batch = node_links[:batch_size]

                    for link in batch:
                        if max_links and link_count >= max_links:
                            break
                        links.append(link)
                        link_count += 1

                    node_links_map[node] = node_links[batch_size:]

                if max_links and link_count >= max_links:
                    break

        return placeholder_links + links
