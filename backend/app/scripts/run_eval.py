"""Ejecuta la evaluación offline contra el golden dataset y genera un reporte.

Requisitos: BD con el corpus demo cargado (python -m app.scripts.seed_demo) y
OPENAI_API_KEY. Cada caso hace varias llamadas al LLM (respuesta + jueces).

    python -m app.scripts.run_eval
    python -m app.scripts.run_eval --limit 3                  # prueba rápida
    python -m app.scripts.run_eval --min-faithfulness 0.9     # falla (exit 1) si baja

Deja en eval/reports/ un .md legible y un .json con el detalle de cada caso.
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.core.config import ROOT_DIR, get_settings
from app.db.session import SessionLocal
from app.models.user import User
from app.services import search as search_service
from app.services.embeddings import get_embedder
from app.services.eval_runner import load_dataset, render_markdown, results_to_json, run_case, summarize
from app.services.llm import get_judge_llm, get_llm
from app.services.permissions import document_access_condition

EVAL_DIR = ROOT_DIR / "eval"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", type=Path, default=EVAL_DIR / "golden_dataset.jsonl")
    parser.add_argument("--out", type=Path, default=EVAL_DIR / "reports")
    parser.add_argument("--limit", type=int, default=None, help="evaluar solo los N primeros casos")
    parser.add_argument("--min-faithfulness", type=float, default=None)
    parser.add_argument("--min-refusal-accuracy", type=float, default=None)
    args = parser.parse_args()

    cases = load_dataset(args.dataset)[: args.limit]
    settings = get_settings()
    llm, judge, embedder = get_llm(), get_judge_llm(), get_embedder()

    with SessionLocal() as db:
        users = {u.email: u for u in db.scalars(select(User).where(User.email.in_({c.as_user for c in cases})))}
        missing = {c.as_user for c in cases} - users.keys()
        if missing:
            print(f"Faltan usuarios {sorted(missing)}: ¿has ejecutado app.scripts.seed_demo?", file=sys.stderr)
            return 2

        def retriever_for(email: str):
            access = document_access_condition(users[email])  # mismos permisos que en el chat

            def retrieve(query: str, top_k: int):
                return search_service.search(
                    db, embedder, query, access=access, top_k=top_k,
                    mode=search_service.SearchMode.HYBRID, min_similarity=settings.rag_min_similarity,
                )

            return retrieve

        results = []
        for i, case in enumerate(cases, start=1):
            print(f"[{i}/{len(cases)}] {case.id}: {case.question}", flush=True)
            results.append(run_case(case, llm, judge, retriever_for))
            db.rollback()  # cierra la transacción de lectura (y sus SET LOCAL) entre casos

    summary = summarize(results)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    args.out.mkdir(parents=True, exist_ok=True)
    title = f"Evaluación RAG · {stamp} · chat={settings.openai_chat_model} · top_k={settings.rag_top_k}"
    (args.out / f"eval-{stamp}.md").write_text(render_markdown(summary, results, title), encoding="utf-8")
    (args.out / f"eval-{stamp}.json").write_text(results_to_json(summary, results), encoding="utf-8")

    print("\n" + render_markdown(summary, results, title).split("## Casos")[0])
    print(f"Reporte: {args.out / f'eval-{stamp}.md'}")

    failed = []
    if args.min_faithfulness is not None and (summary["faithfulness"] or 0) < args.min_faithfulness:
        failed.append(f"fidelidad {summary['faithfulness']} < {args.min_faithfulness}")
    if args.min_refusal_accuracy is not None and (summary["refusal_accuracy"] or 0) < args.min_refusal_accuracy:
        failed.append(f"acierto responder/rechazar {summary['refusal_accuracy']} < {args.min_refusal_accuracy}")
    if failed:
        print("UMBRALES NO SUPERADOS: " + "; ".join(failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
