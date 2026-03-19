"""
동적 심볼 로더 — mixelpixx dynamic_symbol_loader.py 참조

KiCad 10,000+ 심볼 라이브러리에서 심볼 정의를 추출하여
스키매틱에 주입. 괄호 깊이 매칭 + extends 해석 지원.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from loguru import logger


class DynamicSymbolLoader:
    """
    KiCad 심볼 라이브러리 동적 로더

    1. .kicad_sym 파일에서 심볼 S-expression 블록 추출
    2. extends(상속) 관계 해석 → 부모 심볼 인라인
    3. 스키매틱의 lib_symbols 섹션에 주입
    """

    def __init__(self):
        self._lib_cache: dict[str, str] = {}  # lib_name → content

    def find_kicad_symbol_libraries(self) -> list[Path]:
        """KiCad 심볼 라이브러리 디렉토리 탐색"""
        candidates = [
            Path("/usr/share/kicad/symbols"),
            Path("/usr/local/share/kicad/symbols"),
            Path("C:/Program Files/KiCad/9.0/share/kicad/symbols"),
            Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"),
            Path.home() / ".local/share/kicad/9.0/symbols",
            Path.home() / "Documents/KiCad/9.0/3rdparty/symbols",
        ]
        for env in ["KICAD9_SYMBOL_DIR", "KICAD_SYMBOL_DIR"]:
            if env in os.environ:
                candidates.insert(0, Path(os.environ[env]))
        return [p for p in candidates if p.exists() and p.is_dir()]

    def find_library_file(self, library_name: str) -> Optional[Path]:
        """라이브러리 이름으로 .kicad_sym 파일 찾기"""
        for lib_dir in self.find_kicad_symbol_libraries():
            path = lib_dir / f"{library_name}.kicad_sym"
            if path.exists():
                return path
        return None

    def extract_symbol(self, library_name: str, symbol_name: str) -> Optional[str]:
        """라이브러리에서 심볼 S-expression 블록 추출"""
        lib_path = self.find_library_file(library_name)
        if not lib_path:
            logger.warning(f"라이브러리 없음: {library_name}")
            return None

        content = self._get_lib_content(lib_path)
        block = self._extract_symbol_block(content, symbol_name)
        if not block:
            logger.warning(f"심볼 없음: {library_name}:{symbol_name}")
            return None

        # extends 해석
        block = self._resolve_extends(content, symbol_name, block)
        return block

    def inject_into_schematic(
        self, schematic_path: str, library_name: str, symbol_name: str
    ) -> bool:
        """심볼 정의를 스키매틱의 lib_symbols에 주입"""
        full_name = f"{library_name}:{symbol_name}"
        path = Path(schematic_path)
        content = path.read_text(encoding="utf-8")

        if f'(symbol "{full_name}"' in content:
            return True  # 이미 존재

        symbol_block = self.extract_symbol(library_name, symbol_name)
        if not symbol_block:
            return False

        # lib_id 형식으로 변환
        renamed = symbol_block.replace(
            f'(symbol "{symbol_name}"',
            f'(symbol "{full_name}"',
            1,
        )
        # 하위 심볼도 리네임
        renamed = re.sub(
            rf'\(symbol "{re.escape(symbol_name)}_(\d+_\d+)"',
            rf'(symbol "{full_name}_\1"',
            renamed,
        )

        # 들여쓰기 (lib_symbols 내부는 4칸)
        indented = "\n".join("    " + line if line.strip() else line for line in renamed.split("\n"))

        # lib_symbols 블록 끝 찾기
        ls_start = content.find("(lib_symbols")
        if ls_start == -1:
            logger.error("lib_symbols 섹션 없음")
            return False

        depth = 0
        ls_end = ls_start
        for i in range(ls_start, len(content)):
            if content[i] == "(":
                depth += 1
            elif content[i] == ")":
                depth -= 1
                if depth == 0:
                    ls_end = i
                    break

        content = content[:ls_end] + "\n" + indented + "\n  " + content[ls_end:]
        path.write_text(content, encoding="utf-8")
        logger.info(f"심볼 주입: {full_name}")
        return True

    # ─── 내부 헬퍼 ────────────────────────────────────────

    def _get_lib_content(self, path: Path) -> str:
        key = str(path)
        if key not in self._lib_cache:
            self._lib_cache[key] = path.read_text(encoding="utf-8")
        return self._lib_cache[key]

    @staticmethod
    def _extract_symbol_block(text: str, symbol_name: str) -> Optional[str]:
        """괄호 깊이 매칭으로 심볼 블록 추출"""
        lines = text.split("\n")
        start = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            # 최상위 심볼 (하위 _0_1 등 제외)
            if stripped.startswith(f'(symbol "{symbol_name}"') and not re.match(
                r'.*_\d+_\d+"', stripped
            ):
                start = i
                break

        if start is None:
            return None

        depth = 0
        end = None
        for i in range(start, len(lines)):
            for ch in lines[i]:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end is not None:
                break

        if end is None:
            return None
        return "\n".join(lines[start:end + 1])

    def _resolve_extends(self, lib_content: str, symbol_name: str, block: str) -> str:
        """extends(상속) 해석: 부모 심볼을 인라인"""
        extends_match = re.search(r'\(extends "([^"]+)"\)', block)
        if not extends_match:
            return block

        parent_name = extends_match.group(1)
        parent_block = self._extract_symbol_block(lib_content, parent_name)
        if not parent_block:
            return re.sub(r'\s*\(extends "[^"]+"\)\n?', "", block)

        # 자식 프로퍼티 추출
        child_props: dict[str, str] = {}
        for item in self._iter_top_level(block):
            m = re.match(r'\s*\(property "([^"]+)"', item)
            if m:
                child_props[m.group(1)] = item

        # 부모에서 병합
        body_lines = []
        parent_prop_names: set[str] = set()

        for item in self._iter_top_level(parent_block):
            prop_m = re.match(r'\s*\(property "([^"]+)"', item)
            sub_m = re.search(rf'\(symbol "{re.escape(parent_name)}_\d+_\d+"', item)

            if prop_m:
                pname = prop_m.group(1)
                parent_prop_names.add(pname)
                body_lines.append(child_props.get(pname, item))
            elif sub_m:
                body_lines.append(item.replace(f'"{parent_name}_', f'"{symbol_name}_'))
            elif re.match(r'\s*\(extends ', item):
                pass
            else:
                body_lines.append(item)

        for pname, pblock in child_props.items():
            if pname not in parent_prop_names:
                body_lines.append(pblock)

        first_line = parent_block.split("\n")[0].replace(f'"{parent_name}"', f'"{symbol_name}"')
        last_line = parent_block.split("\n")[-1]
        return first_line + "\n" + "\n".join(body_lines) + "\n" + last_line

    @staticmethod
    def _iter_top_level(block: str) -> list[str]:
        """블록 내 최상위 S-expression 항목들을 반환"""
        lines = block.split("\n")
        if len(lines) <= 2:
            return []

        items = []
        depth = 0
        current: list[str] = []

        for line in lines[1:-1]:  # 첫/끝 줄(블록 시작/끝) 제외
            for ch in line:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1

            current.append(line)
            if depth == 0 and current:
                items.append("\n".join(current))
                current = []

        return items
