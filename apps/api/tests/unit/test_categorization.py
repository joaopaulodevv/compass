"""The categorisation rules.

Deterministic and pure, so every case here is a plain function call. The cases that
matter most are the economic ones: a card payment and a transfer to one's own savings
must not be read as spending, because the cash-flow figures depend on that distinction.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from compass_api.domain.categories import ExpenseCategory, is_internal
from compass_api.services.categorization import categorize, normalize

DEBIT = Decimal("-100.00")
CREDIT = Decimal("100.00")


def test_normalize_strips_accents_punctuation_and_case() -> None:
    assert normalize("Supermercado Pão de Açúcar") == ("SUPERMERCADO", "PAO", "DE", "ACUCAR")
    assert normalize("APPLE.COM/BILL  #1234") == ("APPLE", "COM", "BILL", "1234")
    assert normalize("   ") == ()


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("PAGAMENTO CARTAO NUBANK", ExpenseCategory.CREDIT_CARD_PAYMENT),
        ("PGTO CARTAO DE CREDITO", ExpenseCategory.CREDIT_CARD_PAYMENT),
        ("APLICACAO POUPANCA", ExpenseCategory.INTERNAL_TRANSFER),
        ("DEPOSITO POUPANCA", ExpenseCategory.INTERNAL_TRANSFER),
        ("TRANSFERENCIA ENTRE CONTAS", ExpenseCategory.INTERNAL_TRANSFER),
    ],
)
def test_internal_movements_are_recognised(description: str, expected: ExpenseCategory) -> None:
    """These decide whether an amount counts as spending at all."""
    result = categorize(description, DEBIT)

    assert result.category is expected
    assert is_internal(result.category)


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("SALARIO EMPRESA ACME LTDA", ExpenseCategory.INCOME),
        ("BONUS ANUAL", ExpenseCategory.INCOME),
        ("REEMBOLSO PLANO DE SAUDE", ExpenseCategory.INCOME),
        ("RENDIMENTO POUPANCA", ExpenseCategory.INVESTMENT_INCOME),
        ("ALUGUEL IMOBILIARIA CENTRO", ExpenseCategory.HOUSING),
        ("ENERGIA ELETRICA", ExpenseCategory.UTILITIES),
        ("INTERNET FIBRA 500MB", ExpenseCategory.UTILITIES),
        ("PLANO CELULAR FAMILIA", ExpenseCategory.UTILITIES),
        ("NETFLIX.COM", ExpenseCategory.SUBSCRIPTIONS),
        ("SPOTIFY BRASIL", ExpenseCategory.SUBSCRIPTIONS),
        ("SUPERMERCADO PAO DE ACUCAR", ExpenseCategory.GROCERIES),
        ("RESTAURANTE OUTBACK", ExpenseCategory.DINING),
        ("POSTO IPIRANGA", ExpenseCategory.TRANSPORT),
        ("DROGASIL", ExpenseCategory.HEALTH),
        ("ACADEMIA SMART FIT", ExpenseCategory.HEALTH),
        ("TARIFA BANCARIA MENSAL", ExpenseCategory.FEES),
        ("CURSO DE INGLES", ExpenseCategory.EDUCATION),
    ],
)
def test_keyword_rules_cover_the_sandbox_history(
    description: str, expected: ExpenseCategory
) -> None:
    """No provider category is given, so the keyword rules carry this on their own."""
    assert categorize(description, DEBIT).category is expected


def test_more_specific_merchants_win_over_broader_keywords() -> None:
    """`MERCADO LIVRE` is a marketplace, not a grocer, and the rule order must know it."""
    assert categorize("MERCADO LIVRE BR", DEBIT).category is ExpenseCategory.SHOPPING
    assert categorize("SUPERMERCADO BOM PRECO", DEBIT).category is ExpenseCategory.GROCERIES
    assert categorize("AMAZON PRIME BR", DEBIT).category is ExpenseCategory.SUBSCRIPTIONS
    assert categorize("AMAZON MARKETPLACE", DEBIT).category is ExpenseCategory.SHOPPING


def test_keywords_match_whole_tokens_not_substrings() -> None:
    """Substring matching would read `MERCADO` out of an unrelated word."""
    assert categorize("ALIMENTACAO SUPERMERCADISTA", DEBIT).category is ExpenseCategory.OTHER


def test_merchant_name_is_considered_alongside_the_description() -> None:
    result = categorize("COMPRA CARTAO 4321", DEBIT, merchant_name="Drogasil")

    assert result.category is ExpenseCategory.HEALTH


def test_provider_category_is_a_fallback_not_an_authority() -> None:
    """A keyword rule outranks the provider, whose labels are inconsistent in practice."""
    by_keyword = categorize("ALUGUEL", DEBIT, provider_category="groceries")
    assert by_keyword.category is ExpenseCategory.HOUSING
    assert by_keyword.rule == "keyword:housing"

    by_provider = categorize("DEBITO AUTORIZADO 889", DEBIT, provider_category="utilities")
    assert by_provider.category is ExpenseCategory.UTILITIES
    assert by_provider.rule == "provider:utilities"


def test_provider_transfer_label_is_deliberately_not_trusted() -> None:
    """A Pix to a third party is an expense; a provider calls it the same `transfer`
    as a move to one's own savings. Trusting the label would hide real spending."""
    result = categorize("PIX ENVIADO", DEBIT, provider_category="transfer")

    assert result.category is ExpenseCategory.OTHER
    assert not is_internal(result.category)


def test_unexplained_credit_is_income_by_sign() -> None:
    result = categorize("CREDITO EM CONTA 7781", CREDIT)

    assert result.category is ExpenseCategory.INCOME
    assert result.rule == "sign:credit"


def test_unexplained_debit_falls_back_to_other() -> None:
    result = categorize("DEBITO 99812", DEBIT)

    assert result.category is ExpenseCategory.OTHER
    assert result.rule == "fallback"


def test_rule_is_recorded_so_a_categorisation_can_be_audited() -> None:
    assert categorize("NETFLIX.COM", DEBIT).rule == "keyword:subscriptions"


def test_categorization_is_deterministic() -> None:
    first = categorize("POSTO IPIRANGA", DEBIT, merchant_name="Ipiranga")
    second = categorize("POSTO IPIRANGA", DEBIT, merchant_name="Ipiranga")

    assert first == second
