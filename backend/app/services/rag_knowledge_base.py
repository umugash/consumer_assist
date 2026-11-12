"""Verified Knowledge Base & Retrieval module for Consumer Protection in India."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.config import settings

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False


class KnowledgeBase:
    """Manages verified legal and procedural knowledge for Indian consumer protection."""

    def __init__(self, data_file: Optional[str] = None):
        if data_file:
            self.file_path = Path(data_file)
        else:
            self.file_path = Path(settings.DATA_DIR) / "verified_kb.json"

        self.sections: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}
        self.vectorizer = None
        self.tfidf_matrix = None
        self.load_data()

    def load_data(self):
        """Loads and indexes the knowledge base from JSON."""
        if not self.file_path.exists():
            return

        with open(self.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.metadata = data.get("metadata", {})
        self.sections = data.get("sections", [])

        if _SKLEARN_AVAILABLE and self.sections:
            documents = [
                f"{sec.get('title', '')} {sec.get('content', '')} {' '.join(sec.get('tags', []))}"
                for sec in self.sections
            ]
            self.vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
            self.tfidf_matrix = self.vectorizer.fit_transform(documents)

    def query(self, query_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Retrieve most relevant sections for a user grievance or legal question."""
        if not self.sections:
            return []

        if _SKLEARN_AVAILABLE and self.vectorizer is not None and self.tfidf_matrix is not None:
            query_vec = self.vectorizer.transform([query_text])
            similarities = cosine_similarity(query_vec, self.tfidf_matrix)[0]
            top_indices = similarities.argsort()[::-1][:top_k]
            
            results = []
            for idx in top_indices:
                score = float(similarities[idx])
                sec = self.sections[idx]
                results.append({
                    "id": sec.get("id"),
                    "title": sec.get("title"),
                    "category": sec.get("category"),
                    "verification_date": sec.get("verification_date"),
                    "source_url": sec.get("source_url"),
                    "content": sec.get("content"),
                    "relevance_score": round(score, 4),
                })
            return results

        # Fallback keyword match
        query_words = set(query_text.lower().split())
        scored_sections = []
        for sec in self.sections:
            text = (sec.get("title", "") + " " + sec.get("content", "")).lower()
            matches = sum(1 for w in query_words if w in text)
            if matches > 0:
                scored_sections.append((matches, sec))

        scored_sections.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "id": sec.get("id"),
                "title": sec.get("title"),
                "category": sec.get("category"),
                "verification_date": sec.get("verification_date"),
                "source_url": sec.get("source_url"),
                "content": sec.get("content"),
                "relevance_score": min(1.0, score / 10.0),
            }
            for score, sec in scored_sections[:top_k]
        ]

    def get_platform_info(self, platform_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve verified grievance contacts and SLA details for a platform."""
        platform_lower = platform_name.lower()
        for sec in self.sections:
            if sec.get("category") == "platform":
                sec_plat = sec.get("platform", "").lower()
                sec_title = sec.get("title", "").lower()
                if platform_lower in sec_plat or platform_lower in sec_title:
                    return {
                        "platform": sec.get("platform", platform_name),
                        "title": sec.get("title"),
                        "verification_date": sec.get("verification_date"),
                        "source_url": sec.get("source_url"),
                        "content": sec.get("content"),
                    }
        return None

    def get_evidence_checklist(self, issue_category: str) -> Dict[str, Any]:
        """Retrieve verified evidence requirements for a specific complaint category."""
        for sec in self.sections:
            if sec.get("id") == "EVIDENCE_CHECKLIST":
                content = sec.get("content", "")
                return {
                    "source_url": sec.get("source_url"),
                    "verification_date": sec.get("verification_date"),
                    "content": content,
                }
        return {}


# Global instance
knowledge_base = KnowledgeBase()

