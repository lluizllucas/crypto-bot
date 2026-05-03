from src.domain.entities.llm_log import LlmLog
from src.infra.persistence.entities.llm_log_entity import LlmLogEntity


class LlmLogMapper:
    @staticmethod
    def to_domain(orm: LlmLogEntity) -> LlmLog:
        return LlmLog(
            id=orm.id,
            symbol=orm.symbol,
            context=orm.context,
            response=orm.response,
            tool_called=orm.tool_called,
            process=orm.process or "",
            position_id=orm.position_id,
            created_at=orm.created_at,
        )

    @staticmethod
    def to_persistence(
        symbol: str,
        context: dict,
        response: dict,
        process: str = "",
        tool_called: str | None = None,
        position_id: str | None = None,
    ) -> LlmLogEntity:
        return LlmLogEntity(
            symbol=symbol,
            context=context,
            response=response,
            process=process,
            tool_called=tool_called,
            position_id=position_id,
        )
