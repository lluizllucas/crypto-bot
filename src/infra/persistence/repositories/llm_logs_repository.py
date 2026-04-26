import logging

from sqlalchemy.orm import Session

from src.infra.persistence.entities.llm_log_entity import LlmLogEntity
from src.infra.persistence.mappers.llm_log_mapper import LlmLogMapper

log = logging.getLogger(__name__)


class LlmLogsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(
        self,
        symbol: str,
        context: dict,
        response: dict,
        process: str = "",
        tool_called: str | None = None,
        position_id: str | None = None,
    ) -> str | None:
        try:
            entity = LlmLogMapper.to_persistence(
                symbol=symbol,
                context=context,
                response=response,
                process=process,
                tool_called=tool_called,
                position_id=position_id,
            )
            self._session.add(entity)
            self._session.commit()
            self._session.refresh(entity)
            return entity.id
        except Exception as e:
            self._session.rollback()
            log.error(f"Erro ao salvar llm_log ({symbol}): {e}")
            return None

    def get_recent_decisions(self, symbol: str, limit: int = 5) -> list[dict]:
        try:
            rows = (
                self._session.query(LlmLogEntity)
                .filter_by(symbol=symbol, process="bot")
                .order_by(LlmLogEntity.created_at.desc())
                .limit(limit)
                .all()
            )
            result = []
            for row in reversed(rows):
                actions = (row.response or {}).get("actions", [])
                reason  = actions[0]["args"].get("reason", "") if actions else ""
                result.append({
                    "timestamp":   row.created_at.isoformat()[:16],
                    "tool_called": row.tool_called or "none",
                    "reason":      reason,
                })
            return result
        except Exception as e:
            log.error(f"Erro ao buscar decisoes recentes do LLM ({symbol}): {e}")
            return []
