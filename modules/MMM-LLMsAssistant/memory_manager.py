#!/usr/bin/env python3
"""
Memory Manager for MMM-LLMsAssistant
Manages persistent memory storage via a local soul.md file.
Inspired by OpenClaw's SOUL.md concept.
"""

import os
import re
import threading
from typing import Optional, Dict, List


# Valid sections in soul.md
VALID_SECTIONS = ["identity", "user profile", "learned facts", "conversation notes"]


class MemoryManager:
    """Manages reading and writing persistent memories to soul.md"""

    def __init__(self, soul_path: str):
        self.soul_path = soul_path
        self._lock = threading.Lock()
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """Create soul.md with default template if it doesn't exist"""
        if not os.path.exists(self.soul_path):
            default_content = """# Soul - Lens AI Assistant

## Identity
- Name: Lens
- Creator: Gia
- Language: Vietnamese
- Platform: MagicMirror on Raspberry Pi

## User Profile
<!-- The assistant will fill this in as it learns about the user -->

## Learned Facts
<!-- Things learned during conversations -->

## Conversation Notes
<!-- Important reminders and context -->
"""
            with open(self.soul_path, "w", encoding="utf-8") as f:
                f.write(default_content)

    def load(self) -> str:
        """Read the full soul.md content"""
        with self._lock:
            try:
                with open(self.soul_path, "r", encoding="utf-8") as f:
                    return f.read()
            except FileNotFoundError:
                self._ensure_file_exists()
                with open(self.soul_path, "r", encoding="utf-8") as f:
                    return f.read()

    def _save(self, content: str):
        """Write content to soul.md (must be called with lock held)"""
        with open(self.soul_path, "w", encoding="utf-8") as f:
            f.write(content)

    def get_prompt_context(self) -> str:
        """Get soul.md content formatted for system prompt injection"""
        content = self.load()
        if not content.strip():
            return ""
        return f"\n--- PERSISTENT MEMORY (soul.md) ---\n{content}\n--- END PERSISTENT MEMORY ---\n"

    def _parse_sections(self, content: str) -> Dict[str, dict]:
        """
        Parse soul.md into sections.
        Returns dict of {section_name_lower: {"header": original_header, "content": content_lines, "start": start_pos, "end": end_pos}}
        """
        sections = {}
        # Match ## headers
        pattern = re.compile(r'^(## .+)$', re.MULTILINE)
        matches = list(pattern.finditer(content))

        for i, match in enumerate(matches):
            header = match.group(1)
            section_name = header.replace("## ", "").strip().lower()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            section_content = content[start:end]
            sections[section_name] = {
                "header": header,
                "content": section_content,
                "start": start,
                "end": end,
                "header_start": match.start()
            }

        return sections

    def _get_section_entries(self, section_content: str) -> List[str]:
        """Extract non-comment, non-empty entries from a section"""
        entries = []
        for line in section_content.strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("<!--") and not line.endswith("-->"):
                entries.append(line)
        return entries

    def add_memory(self, section: str, content: str) -> Dict:
        """
        Add a new memory entry to the specified section.
        Args:
            section: Section name (e.g., "user profile", "learned facts", "conversation notes")
            content: The memory content to add
        Returns:
            Dict with status and message
        """
        section_lower = section.lower().strip()

        if section_lower not in VALID_SECTIONS:
            return {
                "status": "error",
                "message": f"Invalid section '{section}'. Valid sections: {', '.join(VALID_SECTIONS)}"
            }

        if section_lower == "identity":
            return {
                "status": "error",
                "message": "Cannot modify the Identity section."
            }

        with self._lock:
            try:
                file_content = None
                with open(self.soul_path, "r", encoding="utf-8") as f:
                    file_content = f.read()

                sections = self._parse_sections(file_content)

                if section_lower not in sections:
                    return {"status": "error", "message": f"Section '{section}' not found in soul.md"}

                sec = sections[section_lower]
                # Format the new entry as a list item
                entry = f"- {content}" if not content.startswith("- ") else content

                # Check for duplicate
                existing_entries = self._get_section_entries(sec["content"])
                entry_text = entry.lstrip("- ").strip()
                for existing in existing_entries:
                    if existing.lstrip("- ").strip().lower() == entry_text.lower():
                        return {"status": "exists", "message": f"Memory already exists in '{section}'"}

                # Remove HTML comment placeholder if present
                section_content = sec["content"]
                section_content = re.sub(r'\s*<!--[^>]+-->\s*', '\n', section_content)

                # Append entry
                new_section_content = section_content.rstrip() + "\n" + entry + "\n\n"

                # Rebuild file
                new_content = file_content[:sec["start"]] + new_section_content + file_content[sec["end"]:]
                self._save(new_content)

                return {"status": "success", "message": f"Memory saved to '{section}': {content}"}

            except Exception as e:
                return {"status": "error", "message": f"Failed to save memory: {str(e)}"}

    def remove_memory(self, section: str, content: str) -> Dict:
        """
        Remove a memory entry from the specified section.
        Args:
            section: Section name
            content: The memory content to remove (partial match supported)
        Returns:
            Dict with status and message
        """
        section_lower = section.lower().strip()

        if section_lower == "identity":
            return {"status": "error", "message": "Cannot modify the Identity section."}

        with self._lock:
            try:
                file_content = None
                with open(self.soul_path, "r", encoding="utf-8") as f:
                    file_content = f.read()

                sections = self._parse_sections(file_content)

                if section_lower not in sections:
                    return {"status": "error", "message": f"Section '{section}' not found"}

                sec = sections[section_lower]
                lines = sec["content"].split("\n")
                content_lower = content.lower().strip()

                new_lines = []
                removed = False
                for line in lines:
                    line_text = line.lstrip("- ").strip().lower()
                    if content_lower in line_text and not removed:
                        removed = True
                        continue
                    new_lines.append(line)

                if not removed:
                    return {"status": "not_found", "message": f"No matching memory found in '{section}'"}

                new_section_content = "\n".join(new_lines)
                new_content = file_content[:sec["start"]] + new_section_content + file_content[sec["end"]:]
                self._save(new_content)

                return {"status": "success", "message": f"Memory removed from '{section}'"}

            except Exception as e:
                return {"status": "error", "message": f"Failed to remove memory: {str(e)}"}

    def list_memories(self, section: Optional[str] = None) -> Dict:
        """
        List all memories, optionally filtered by section.
        Args:
            section: Optional section name to filter
        Returns:
            Dict with memories organized by section
        """
        try:
            file_content = self.load()
            sections = self._parse_sections(file_content)

            result = {}
            for sec_name, sec_data in sections.items():
                if section and sec_name != section.lower().strip():
                    continue
                entries = self._get_section_entries(sec_data["content"])
                if entries:
                    result[sec_name] = [e.lstrip("- ").strip() for e in entries]

            return {"status": "success", "memories": result}

        except Exception as e:
            return {"status": "error", "message": f"Failed to list memories: {str(e)}"}
