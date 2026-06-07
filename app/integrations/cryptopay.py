from decimal import Decimal

from aiocryptopay import AioCryptoPay, Networks

from app.config import Settings


class CryptoPayService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: AioCryptoPay | None = None

    def _network(self) -> Networks:
        if self._settings.crypto_pay_network.lower() == "test_net":
            return Networks.TEST_NET
        return Networks.MAIN_NET

    async def start(self) -> None:
        if not self._settings.crypto_pay_token:
            return
        self._client = AioCryptoPay(
            token=self._settings.crypto_pay_token,
            network=self._network(),
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()

    async def create_invoice(
        self,
        asset: str,
        amount: Decimal,
        description: str,
    ):
        if self._client is None:
            raise RuntimeError("CRYPTO_PAY_TOKEN не настроен")
        return await self._client.create_invoice(
            asset=asset,
            amount=float(amount),
            description=description,
        )

    async def get_invoice(self, invoice_id: int):
        if self._client is None:
            raise RuntimeError("CRYPTO_PAY_TOKEN не настроен")
        invoices = await self._client.get_invoices(invoice_ids=invoice_id)
        return invoices[0] if invoices else None
