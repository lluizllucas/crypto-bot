import logging

from sqlalchemy.orm import Session

from src.domain.entities.position import Position
from src.infra.persistence.entities.open_position_entity import OpenPositionEntity
from src.infra.persistence.mappers.open_position_mapper import OpenPositionMapper

log = logging.getLogger(__name__)


class OpenPositionsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def load_all(self) -> dict[str, list[Position]]:
        try:
            rows = self._session.query(OpenPositionEntity).all()
            result: dict[str, list[Position]] = {}
            for row in rows:
                symbol = row.symbol
                result.setdefault(symbol, []).append(
                    OpenPositionMapper.to_domain(row))
            log.info(
                f"Posicoes carregadas do banco: {sum(len(v) for v in result.values())} lote(s)")
            return result
        except Exception as e:
            log.error(f"Erro ao carregar posicoes do banco: {e}")
            return {}

    def save(self, symbol: str, position: Position) -> str | None:
        try:
            entity = OpenPositionMapper.to_persistence(symbol, position)
            self._session.add(entity)
            self._session.commit()
            self._session.refresh(entity)
            return entity.id
        except Exception as e:
            self._session.rollback()
            log.error(f"Erro ao salvar posicao no banco ({symbol}): {e}")
            return None

    def update(self, position: Position) -> None:
        if not position.db_id:
            return
        try:
            self._session.query(OpenPositionEntity).filter_by(id=position.db_id).update({
                "sl":            position.sl,
                "tp":            position.tp,
                "tp_hold_count": position.tp_hold_count,
            })
            self._session.commit()
        except Exception as e:
            self._session.rollback()
            log.error(
                f"Erro ao atualizar posicao no banco (id={position.db_id}): {e}")

    def delete(self, position_id: str) -> None:
        try:
            self._session.query(OpenPositionEntity).filter_by(
                id=position_id).delete()
            self._session.commit()
        except Exception as e:
            self._session.rollback()
            log.error(
                f"Erro ao remover posicao do banco (id={position_id}): {e}")

    def delete_all_by_symbol(self, symbol: str) -> None:
        try:
            self._session.query(OpenPositionEntity).filter_by(
                symbol=symbol).delete()
            self._session.commit()
        except Exception as e:
            self._session.rollback()
            log.error(f"Erro ao remover posicoes do banco ({symbol}): {e}")

    def get_by_symbol(self, symbol: str) -> list[Position]:
        try:
            rows = self._session.query(
                OpenPositionEntity).filter_by(symbol=symbol).all()
            return [OpenPositionMapper.to_domain(row) for row in rows]
        except Exception as e:
            log.error(f"Erro ao buscar posicoes do banco ({symbol}): {e}")
            return []

    def get_by_id(self, position_id: str) -> Position | None:
        try:
            row = self._session.query(OpenPositionEntity).filter_by(
                id=position_id).first()
            return OpenPositionMapper.to_domain(row) if row else None
        except Exception as e:
            log.error(
                f"Erro ao buscar posicao do banco (id={position_id}): {e}")
            return None

    def count_by_symbol(self, symbol: str) -> int:
        try:
            return self._session.query(OpenPositionEntity).filter_by(symbol=symbol).count()
        except Exception as e:
            log.error(f"Erro ao contar posicoes no banco ({symbol}): {e}")
            return 0
