"""Rule-based expense categorisation.

Deterministic by design. An LLM must never decide a category: the result feeds the
cash-flow and saving-capacity figures, and those have to be reproducible and auditable
(ADR-0005). A rule that fires is recorded on the transaction, so any categorisation can
be traced back to the reason for it.

Matching happens on whole token sequences, not substrings, so `MERCADO LIVRE` does not
turn a marketplace purchase into groceries and a keyword cannot fire on a fragment of an
unrelated word.

Precedence:

1. Keyword rules, in declared order. They are ours, they are testable, and they are the
   only way to settle the economically decisive cases - a card payment and a transfer to
   one's own savings must never be counted as spending.
2. The provider's own category, for the labels that are unambiguous. `transfer` is not
   among them: a Pix to a third party is an expense, while moving money to your own
   savings is not, and the provider calls both the same thing.
3. The sign of the amount. A credit nothing else explains is income; a debit nothing
   else explains is `OTHER`, which is a better answer than a confident wrong one.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

from compass_api.domain.categories import Categorization, ExpenseCategory

_NON_ALPHANUMERIC = re.compile(r"[^A-Z0-9]+")


def normalize(text: str) -> tuple[str, ...]:
    """Upper-case, strip accents and punctuation, and split into tokens.

    `Supermercado Pão de Açúcar` -> `("SUPERMERCADO", "PAO", "DE", "ACUCAR")`.
    """
    decomposed = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return tuple(token for token in _NON_ALPHANUMERIC.split(decomposed.upper()) if token)


@dataclass(frozen=True, slots=True)
class KeywordRule:
    """Fires when any of its keywords appears as a contiguous token sequence."""

    name: str
    category: ExpenseCategory
    keywords: tuple[tuple[str, ...], ...]

    def matches(self, tokens: tuple[str, ...]) -> bool:
        return any(_contains(tokens, keyword) for keyword in self.keywords)


def _contains(tokens: tuple[str, ...], keyword: tuple[str, ...]) -> bool:
    if not keyword or len(keyword) > len(tokens):
        return False
    return any(
        tokens[start : start + len(keyword)] == keyword
        for start in range(len(tokens) - len(keyword) + 1)
    )


def _rule(name: str, category: ExpenseCategory, *keywords: str) -> KeywordRule:
    return KeywordRule(
        name=name, category=category, keywords=tuple(normalize(word) for word in keywords)
    )


#: Ordered. The internal-movement rules come first because they decide whether an amount
#: counts as spending at all; more specific merchants come before broader ones.
RULES: tuple[KeywordRule, ...] = (
    _rule(
        "credit-card-payment",
        ExpenseCategory.CREDIT_CARD_PAYMENT,
        "pagamento cartao",
        "pgto cartao",
        "fatura cartao",
        "pagamento fatura",
    ),
    _rule(
        "internal-transfer",
        ExpenseCategory.INTERNAL_TRANSFER,
        "aplicacao poupanca",
        "deposito poupanca",
        "resgate poupanca",
        "aplicacao cdb",
        "resgate cdb",
        "transferencia entre contas",
        "transferencia mesma titularidade",
    ),
    _rule(
        "investment-income",
        ExpenseCategory.INVESTMENT_INCOME,
        "rendimento",
        "rendimentos",
        "dividendos",
        "juros poupanca",
    ),
    _rule(
        "income",
        ExpenseCategory.INCOME,
        "salario",
        "pro labore",
        "bonus",
        "ferias",
        "decimo terceiro",
        "reembolso",
        "restituicao",
    ),
    _rule(
        "subscriptions",
        ExpenseCategory.SUBSCRIPTIONS,
        "netflix",
        "spotify",
        "amazon prime",
        "prime video",
        "disney plus",
        "hbo",
        "youtube premium",
        "apple com bill",
        "google one",
        "icloud",
        "deezer",
        "globoplay",
        "assinatura",
    ),
    _rule(
        "shopping",
        ExpenseCategory.SHOPPING,
        "mercado livre",
        "mercadolivre",
        "shopee",
        "magazine luiza",
        "americanas",
        "amazon",
        "aliexpress",
    ),
    _rule(
        "groceries",
        ExpenseCategory.GROCERIES,
        "supermercado",
        "mercado",
        "hipermercado",
        "pao de acucar",
        "carrefour",
        "assai",
        "atacadao",
        "hortifruti",
        "emporio",
        "sacolao",
    ),
    _rule(
        "dining",
        ExpenseCategory.DINING,
        "restaurante",
        "ifood",
        "rappi",
        "lanchonete",
        "pizzaria",
        "outback",
        "mcdonalds",
        "burger king",
        "padaria",
        "cafeteria",
        "starbucks",
    ),
    _rule(
        "transport",
        ExpenseCategory.TRANSPORT,
        "posto",
        "ipiranga",
        "shell",
        "petrobras",
        "combustivel",
        "uber",
        "cabify",
        "taxi",
        "estacionamento",
        "pedagio",
        "metro",
        "passagem aerea",
    ),
    _rule(
        "health",
        ExpenseCategory.HEALTH,
        "drogasil",
        "drogaria",
        "farmacia",
        "raia",
        "panvel",
        "hospital",
        "clinica",
        "laboratorio",
        "plano de saude",
        "unimed",
        "odonto",
        "academia",
        "smart fit",
        "gympass",
    ),
    _rule(
        "utilities",
        ExpenseCategory.UTILITIES,
        "energia eletrica",
        "energia",
        "enel",
        "cpfl",
        "light",
        "copel",
        "sabesp",
        "saneamento",
        "agua e esgoto",
        "comgas",
        "internet",
        "fibra",
        "banda larga",
        "vivo",
        "claro",
        "plano celular",
        "telefone",
    ),
    _rule(
        "housing",
        ExpenseCategory.HOUSING,
        "aluguel",
        "imobiliaria",
        "condominio",
        "iptu",
        "financiamento imobiliario",
    ),
    _rule(
        "education",
        ExpenseCategory.EDUCATION,
        "escola",
        "faculdade",
        "universidade",
        "mensalidade escolar",
        "curso",
        "udemy",
        "alura",
    ),
    _rule(
        "fees",
        ExpenseCategory.FEES,
        "tarifa",
        "tarifa bancaria",
        "anuidade",
        "iof",
        "multa",
        "juros de mora",
    ),
)

#: Provider labels specific enough to trust. `transfer` is excluded on purpose - see the
#: module docstring.
PROVIDER_CATEGORIES: dict[str, ExpenseCategory] = {
    "income": ExpenseCategory.INCOME,
    "investment_income": ExpenseCategory.INVESTMENT_INCOME,
    "credit_card_payment": ExpenseCategory.CREDIT_CARD_PAYMENT,
    "housing": ExpenseCategory.HOUSING,
    "utilities": ExpenseCategory.UTILITIES,
    "groceries": ExpenseCategory.GROCERIES,
    "dining": ExpenseCategory.DINING,
    "transport": ExpenseCategory.TRANSPORT,
    "health": ExpenseCategory.HEALTH,
    "education": ExpenseCategory.EDUCATION,
    "subscriptions": ExpenseCategory.SUBSCRIPTIONS,
    "shopping": ExpenseCategory.SHOPPING,
    "fees": ExpenseCategory.FEES,
}


def categorize(
    description: str,
    amount: Decimal,
    merchant_name: str | None = None,
    provider_category: str | None = None,
) -> Categorization:
    """Classify one movement. Pure, deterministic, order-independent of the caller."""
    tokens = normalize(f"{description} {merchant_name or ''}")

    for rule in RULES:
        if rule.matches(tokens):
            return Categorization(category=rule.category, rule=f"keyword:{rule.name}")

    if provider_category:
        mapped = PROVIDER_CATEGORIES.get(provider_category.strip().lower())
        if mapped is not None:
            return Categorization(category=mapped, rule=f"provider:{provider_category}")

    if amount > 0:
        return Categorization(category=ExpenseCategory.INCOME, rule="sign:credit")

    return Categorization(category=ExpenseCategory.OTHER, rule="fallback")
