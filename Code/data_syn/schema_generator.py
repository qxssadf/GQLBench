#!/usr/bin/env python3
import json

import os

from datetime import datetime

from typing import Dict, List, Any

from dataclasses import dataclass, asdict


@dataclass
class BusinessConstraint:

    name: str
    constraint_type: str
    description: str
    condition: str
    error_message: str = ""
    affected_entities: List[str] = None
    python_check_function: str = None
    python_check_params: Dict[str, Any] = None
    constraint_metadata: Dict[str, Any] = None


@dataclass
class Property:

    name: str
    type: str
    required: bool = True
    unique: bool = False
    indexed: bool = False
    min_value: Any = None
    max_value: Any = None
    allowed_values: List[str | int | float] = None
    is_category: bool = False
    is_id: bool = False
    description: str = ""


@dataclass
class NodeType:

    name: str
    properties: List[Property]
    labels: List[str] = None


@dataclass
class RelationshipType:

    name: str
    from_node: str
    to_node: str
    properties: List[Property] = None
    directed: bool = True
    cardinality: str = "N:M"
    max_connections_per_from: int = None
    max_connections_per_to: int = None


@dataclass
class CyclePattern:

    id: str
    name: str
    description: str
    cycle_path: List[str]
    cycle_length: int
    is_valid: bool
    explanation: str
    business_logic: str
    node_types_involved: List[str]
    relationship_types_involved: List[str]
    constraints: Dict[str, Any] = None
    instance_cycle_description: str = ""
    example_cycle: Dict[str, Any] = None


@dataclass
class DatabaseSchema:

    name: str
    domain: str
    description: str
    node_types: List[NodeType]
    relationship_types: List[RelationshipType]
    business_constraints: List[BusinessConstraint] = None
    cycle_patterns: List[CyclePattern] = None


class SchemaGenerator:
    def __init__(self):
        self.domains = {
            "Finance": self._generate_finance_schemas,
            "Legal": self._generate_legal_schemas,
            "Sports": self._generate_sports_schemas,
            "Education": self._generate_education_schemas,
            "Social": self._generate_social_schemas,
            "Healthcare": self._generate_healthcare_schemas,
            "E-commerce": self._generate_ecommerce_schemas,
            "Transportation": self._generate_transportation_schemas,
            "Real Estate": self._generate_real_estate_schemas,
            "Entertainment": self._generate_entertainment_schemas,
        }

    def generate_all_schemas(self) -> Dict[str, List[DatabaseSchema]]:
        all_schemas = {}
        for (domain, generator_func) in self.domains.items():
            all_schemas[domain] = generator_func()
        return all_schemas

    def _generate_finance_schemas(self) -> List[DatabaseSchema]:
        schemas = []
        bank_schema = DatabaseSchema(
            name="banking_system",
            domain="Finance",
            description="Banking System Graph Database Schema",
            node_types=[
                NodeType(
                    "Customer",
                    [
                        Property(
                            "customer_id",
                            "string",
                            unique=True,
                            indexed=True,
                            description="Unique customer identifier",
                        ),
                        Property("name", "string", description="Customer name"),
                        Property(
                            "age",
                            "int",
                            min_value=18,
                            max_value=80,
                            description="Customer age",
                        ),
                        Property("phone", "string", description="Phone number"),
                        Property("email", "string", description="Email address"),
                        Property(
                            "address", "string", description="Residential address"
                        ),
                        Property(
                            "credit_score",
                            "int",
                            min_value=300,
                            max_value=850,
                            description="Credit score",
                        ),
                        Property(
                            "registration_date", "date", description="Registration date"
                        ),
                    ],
                ),
                NodeType(
                    "Account",
                    [
                        Property(
                            "account_id",
                            "string",
                            unique=True,
                            indexed=True,
                            description="Unique account identifier",
                        ),
                        Property(
                            "account_type",
                            "string",
                            is_category=True,
                            allowed_values=[
                                "savings",
                                "checking",
                                "credit_card",
                                "investment",
                            ],
                            description="Account type",
                        ),
                        Property(
                            "balance",
                            "float",
                            min_value=0.0,
                            max_value=10000000.0,
                            description="Account balance",
                        ),
                        Property(
                            "currency",
                            "string",
                            is_category=True,
                            allowed_values=["CNY", "USD", "EUR", "JPY"],
                            description="Currency type",
                        ),
                        Property(
                            "opening_date", "date", description="Account opening date"
                        ),
                        Property(
                            "status",
                            "string",
                            is_category=True,
                            allowed_values=["active", "inactive", "frozen", "closed"],
                            description="Account status",
                        ),
                    ],
                ),
                NodeType(
                    "Transaction",
                    [
                        Property(
                            "transaction_id",
                            "string",
                            unique=True,
                            indexed=True,
                            description="Unique transaction identifier",
                        ),
                        Property(
                            "amount",
                            "float",
                            min_value=0.01,
                            max_value=1000000.0,
                            description="Transaction amount",
                        ),
                        Property(
                            "transaction_type",
                            "string",
                            is_category=True,
                            allowed_values=[
                                "deposit",
                                "withdrawal",
                                "transfer",
                                "payment",
                                "investment",
                            ],
                            description="Transaction type",
                        ),
                        Property(
                            "description",
                            "string",
                            description="Transaction description",
                        ),
                        Property(
                            "timestamp", "datetime", description="Transaction timestamp"
                        ),
                        Property(
                            "status",
                            "string",
                            is_category=True,
                            allowed_values=[
                                "pending",
                                "completed",
                                "failed",
                                "cancelled",
                            ],
                            description="Transaction status",
                        ),
                    ],
                ),
                NodeType(
                    "Bank",
                    [
                        Property(
                            "bank_id",
                            "string",
                            unique=True,
                            indexed=True,
                            description="Unique bank identifier",
                        ),
                        Property("bank_name", "string", description="Bank name"),
                        Property("location", "string", description="Bank location"),
                        Property(
                            "established_year",
                            "int",
                            min_value=1800,
                            max_value=2024,
                            description="Established year",
                        ),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType(
                    "OWNS",
                    "Customer",
                    "Account",
                    cardinality="1:N",
                    max_connections_per_from=5,
                ),
                RelationshipType(
                    "TRANSFERS_TO", "Account", "Account", cardinality="N:M"
                ),
                RelationshipType(
                    "FROM_ACCOUNT",
                    "Transaction",
                    "Account",
                    cardinality="1:1",
                    max_connections_per_from=1,
                    max_connections_per_to=1,
                ),
                RelationshipType(
                    "TO_ACCOUNT",
                    "Transaction",
                    "Account",
                    cardinality="1:1",
                    max_connections_per_from=1,
                    max_connections_per_to=1,
                ),
                RelationshipType(
                    "BELONGS_TO",
                    "Account",
                    "Bank",
                    cardinality="N:1",
                    max_connections_per_to=1,
                ),
                RelationshipType("CUSTOMER_OF", "Customer", "Bank", cardinality="N:M"),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="transfer_balance_consistency",
                    constraint_type="business_logic",
                    description="Transfer must maintain balance consistency: from account balance decreases, to account balance increases, total amount remains unchanged",
                    condition="transfer_amount <= from_account.balance AND from_account.balance_after = from_account.balance_before - transfer_amount AND to_account.balance_after = to_account.balance_before + transfer_amount",
                    error_message="Transfer amount exceeds account balance or balance calculation inconsistent",
                    affected_entities=["Account", "Transaction"],
                    python_check_function="check_transfer_balance_consistency",
                    python_check_params={
                        "check_type": "balance_consistency",
                        "amount_property": "amount",
                        "from_balance_property": "balance",
                        "to_balance_property": "balance",
                    },
                    constraint_metadata={
                        "check_type": "business_logic",
                        "complexity": "high",
                        "use_llm": True,
                    },
                ),
                BusinessConstraint(
                    name="account_balance_calculation",
                    constraint_type="numerical_consistency",
                    description="Account balance must equal initial balance plus all deposits minus all withdrawals",
                    condition="account.balance = account.initial_balance + SUM(CASE WHEN transaction_type = 'deposit' THEN amount ELSE 0 END) - SUM(CASE WHEN transaction_type = 'withdrawal' THEN amount ELSE 0 END)",
                    error_message="Account balance calculation inconsistent",
                    affected_entities=["Account", "Transaction"],
                    python_check_function="check_numerical_consistency",
                    python_check_params={
                        "check_type": "balance_calculation",
                        "target_property": "balance",
                        "calculation_formula": "initial_balance + deposits - withdrawals",
                        "deposit_condition": "transaction_type = 'deposit'",
                        "withdrawal_condition": "transaction_type = 'withdrawal'",
                    },
                    constraint_metadata={
                        "check_type": "numerical_consistency",
                        "complexity": "medium",
                        "use_llm": False,
                    },
                ),
                BusinessConstraint(
                    name="transaction_status_consistency",
                    constraint_type="state_consistency",
                    description="Completed transactions must have valid account references",
                    condition="status = 'completed' IMPLIES (from_account_id IS NOT NULL AND to_account_id IS NOT NULL)",
                    error_message="Completed transaction missing account references",
                    affected_entities=["Transaction", "Account"],
                ),
                BusinessConstraint(
                    name="account_ownership_integrity",
                    constraint_type="referential_integrity",
                    description="Account must belong to a valid customer",
                    condition="account.customer_id IS NOT NULL AND EXISTS(SELECT 1 FROM Customer WHERE customer_id = account.customer_id)",
                    error_message="Account missing valid customer reference",
                    affected_entities=["Account", "Customer"],
                ),
                BusinessConstraint(
                    name="transaction_temporal_consistency",
                    constraint_type="temporal_consistency",
                    description="Transaction timestamp cannot be in the future",
                    condition="transaction.timestamp <= NOW()",
                    error_message="Transaction timestamp cannot be in the future",
                    affected_entities=["Transaction"],
                ),
                BusinessConstraint(
                    name="cross_bank_transfer_validation",
                    constraint_type="business_logic",
                    description="Cross-bank transfers must be explicitly marked as external transfers",
                    condition="from_account.bank_id != to_account.bank_id IMPLIES transaction_type = 'external_transfer'",
                    error_message="Invalid cross-bank transaction type",
                    affected_entities=["Transaction", "Account"],
                ),
            ],
            cycle_patterns=[
                CyclePattern(
                    id="banking_cycle_1",
                    name="account_transfer_cycle",
                    description="Account-Transfer-Account cycle pattern",
                    cycle_path=[
                        "Account",
                        "TRANSFERS_TO",
                        "Account",
                        "TRANSFERS_TO",
                        "Account",
                        "TRANSFERS_TO",
                        "Account",
                    ],
                    cycle_length=7,
                    is_valid=True,
                    explanation="Accounts can transfer funds to each other, forming a cycle through transfer relationships",
                    business_logic="Follows banking business logic, accounts can transfer funds in cycles (e.g., Account A transfers to B, B transfers to C, C transfers back to A)",
                    node_types_involved=["Account"],
                    relationship_types_involved=["TRANSFERS_TO"],
                    instance_cycle_description="Multiple accounts transfer funds to each other, eventually returning to the starting account",
                    example_cycle={
                        "description": "Three accounts form a transfer cycle",
                        "cycle_instances": [
                            {
                                "type": "Account",
                                "id": "Account_001",
                                "account_type": "savings",
                            },
                            {
                                "type": "TRANSFERS_TO",
                                "id": "TRANSFERS_TO_001",
                                "from": "Account_001",
                                "to": "Account_002",
                            },
                            {
                                "type": "Account",
                                "id": "Account_002",
                                "account_type": "checking",
                            },
                            {
                                "type": "TRANSFERS_TO",
                                "id": "TRANSFERS_TO_002",
                                "from": "Account_002",
                                "to": "Account_003",
                            },
                            {
                                "type": "Account",
                                "id": "Account_003",
                                "account_type": "investment",
                            },
                            {
                                "type": "TRANSFERS_TO",
                                "id": "TRANSFERS_TO_003",
                                "from": "Account_003",
                                "to": "Account_001",
                            },
                        ],
                    },
                    constraints={
                        "min_cycle_length": 3,
                        "max_cycle_length": 10,
                        "business_rules": [
                            "Transfer amount cannot exceed source account balance",
                            "Each account in the cycle must have sufficient balance for outgoing transfers",
                        ],
                    },
                )
            ],
        )
        schemas.append(bank_schema)
        stock_schema = DatabaseSchema(
            name="stock_trading",
            domain="Finance",
            description="Stock Trading System Graph Database Schema",
            node_types=[
                NodeType(
                    "Investor",
                    [
                        Property(
                            "investor_id",
                            "string",
                            unique=True,
                            indexed=True,
                            description="Unique investor identifier",
                        ),
                        Property("name", "string", description="Investor name"),
                        Property(
                            "investment_style",
                            "string",
                            is_category=True,
                            allowed_values=[
                                "conservative",
                                "moderate",
                                "aggressive",
                                "speculative",
                            ],
                            description="Investment style",
                        ),
                        Property(
                            "risk_tolerance",
                            "string",
                            is_category=True,
                            allowed_values=["low", "medium", "high"],
                            description="Risk tolerance",
                        ),
                        Property(
                            "total_assets",
                            "float",
                            min_value=1000.0,
                            max_value=100000000.0,
                            description="Total assets",
                        ),
                    ],
                ),
                NodeType(
                    "Stock",
                    [
                        Property(
                            "symbol",
                            "string",
                            unique=True,
                            indexed=True,
                            description="Stock symbol",
                        ),
                        Property("company_name", "string", description="Company name"),
                        Property(
                            "sector",
                            "string",
                            is_category=True,
                            allowed_values=[
                                "technology",
                                "finance",
                                "healthcare",
                                "energy",
                                "consumer",
                                "industrial",
                                "materials",
                                "utilities",
                            ],
                            description="Industry sector",
                        ),
                        Property(
                            "market_cap",
                            "float",
                            min_value=1000000.0,
                            max_value=1000000000000.0,
                            description="Market capitalization",
                        ),
                        Property(
                            "current_price",
                            "float",
                            min_value=0.01,
                            max_value=10000.0,
                            description="Current price",
                        ),
                        Property(
                            "dividend_yield",
                            "float",
                            min_value=0.0,
                            max_value=0.2,
                            description="Dividend yield",
                        ),
                    ],
                ),
                NodeType(
                    "Trade",
                    [
                        Property(
                            "trade_id",
                            "string",
                            unique=True,
                            indexed=True,
                            description="Unique trade identifier",
                        ),
                        Property(
                            "quantity",
                            "int",
                            min_value=1,
                            max_value=1000000,
                            description="Trade quantity",
                        ),
                        Property(
                            "price",
                            "float",
                            min_value=0.01,
                            max_value=10000.0,
                            description="Trade price",
                        ),
                        Property(
                            "trade_type",
                            "string",
                            is_category=True,
                            allowed_values=["buy", "sell", "short", "cover"],
                            description="Trade type",
                        ),
                        Property(
                            "timestamp", "datetime", description="Trade timestamp"
                        ),
                    ],
                ),
                NodeType(
                    "Company",
                    [
                        Property(
                            "company_id",
                            "string",
                            unique=True,
                            indexed=True,
                            description="Unique company identifier",
                        ),
                        Property("name", "string", description="Company name"),
                        Property(
                            "industry",
                            "string",
                            is_category=True,
                            allowed_values=[
                                "technology",
                                "finance",
                                "healthcare",
                                "energy",
                                "consumer",
                                "industrial",
                                "materials",
                                "utilities",
                            ],
                            description="Industry",
                        ),
                        Property(
                            "founded_year",
                            "int",
                            min_value=1800,
                            max_value=2024,
                            description="Founded year",
                        ),
                        Property(
                            "revenue",
                            "float",
                            min_value=0.0,
                            max_value=1000000000000.0,
                            description="Annual revenue",
                        ),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType("TRADES", "Investor", "Stock", cardinality="N:M"),
                RelationshipType(
                    "EXECUTES",
                    "Trade",
                    "Stock",
                    cardinality="1:1",
                    max_connections_per_from=1,
                    max_connections_per_to=1,
                ),
                RelationshipType(
                    "INVOLVES",
                    "Trade",
                    "Investor",
                    cardinality="1:1",
                    max_connections_per_from=1,
                    max_connections_per_to=1,
                ),
                RelationshipType(
                    "ISSUES",
                    "Company",
                    "Stock",
                    cardinality="1:N",
                    max_connections_per_from=10,
                ),
                RelationshipType(
                    "COMPETES_WITH", "Company", "Company", cardinality="N:M"
                ),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="trade_capital_consistency",
                    constraint_type="business_logic",
                    description="Buy trade total amount cannot exceed investor's total assets",
                    condition="trade_type = 'buy' IMPLIES (quantity * price <= investor.total_assets)",
                    error_message="Buy trade amount exceeds investor's total assets",
                    affected_entities=["Trade", "Investor"],
                ),
                BusinessConstraint(
                    name="stock_holding_consistency",
                    constraint_type="numerical_consistency",
                    description="Sell quantity cannot exceed current holding quantity",
                    condition="trade_type = 'sell' IMPLIES (quantity <= current_holding_quantity)",
                    error_message="Sell quantity exceeds current holding quantity",
                    affected_entities=["Trade", "Stock"],
                ),
                BusinessConstraint(
                    name="short_selling_consistency",
                    constraint_type="business_logic",
                    description="Short selling must have sufficient margin",
                    condition="trade_type = 'short' IMPLIES (quantity * price * 0.5 <= investor.total_assets)",
                    error_message="Insufficient margin for short selling",
                    affected_entities=["Trade", "Investor"],
                ),
                BusinessConstraint(
                    name="trade_price_reasonableness",
                    constraint_type="business_logic",
                    description="Trade price cannot deviate from current price by more than 10%",
                    condition="ABS(trade.price - stock.current_price) / stock.current_price <= 0.1",
                    error_message="Trade price deviates too much from current price",
                    affected_entities=["Trade", "Stock"],
                ),
                BusinessConstraint(
                    name="market_hours_consistency",
                    constraint_type="temporal_consistency",
                    description="Trades must be executed during market hours",
                    condition="HOUR(trade.timestamp) BETWEEN 9 AND 16 AND WEEKDAY(trade.timestamp) BETWEEN 1 AND 5",
                    error_message="Trade time is outside market hours",
                    affected_entities=["Trade"],
                ),
                BusinessConstraint(
                    name="company_stock_consistency",
                    constraint_type="referential_integrity",
                    description="Stock must belong to a valid company",
                    condition="stock.company_id IS NOT NULL AND EXISTS(SELECT 1 FROM Company WHERE company_id = stock.company_id)",
                    error_message="Stock is missing a valid company reference",
                    affected_entities=["Stock", "Company"],
                ),
            ],
            cycle_patterns=[],
        )
        schemas.append(stock_schema)
        insurance_schema = DatabaseSchema(
            name="insurance_system",
            domain="Finance",
            description="Insurance System Graph Database Schema",
            node_types=[
                NodeType(
                    "Policyholder",
                    [
                        Property(
                            "policyholder_id",
                            "string",
                            unique=True,
                            indexed=True,
                            description="Unique policyholder identifier",
                        ),
                        Property("name", "string", description="Policyholder name"),
                        Property(
                            "age",
                            "int",
                            min_value=18,
                            max_value=80,
                            description="Policyholder age",
                        ),
                        Property(
                            "occupation",
                            "string",
                            is_category=True,
                            allowed_values=[
                                "teacher",
                                "doctor",
                                "engineer",
                                "lawyer",
                                "civil_servant",
                                "entrepreneur",
                                "student",
                                "retired",
                            ],
                            description="Occupation",
                        ),
                        Property(
                            "health_status",
                            "string",
                            is_category=True,
                            allowed_values=[
                                "healthy",
                                "sub_healthy",
                                "chronic_disease",
                                "serious_illness",
                            ],
                            description="Health status",
                        ),
                        Property(
                            "risk_level",
                            "string",
                            is_category=True,
                            allowed_values=["low", "medium", "high"],
                            description="Risk level",
                        ),
                    ],
                ),
                NodeType(
                    "Policy",
                    [
                        Property(
                            "policy_id",
                            "string",
                            unique=True,
                            indexed=True,
                            description="Unique policy identifier",
                        ),
                        Property(
                            "policy_type",
                            "string",
                            is_category=True,
                            allowed_values=[
                                "life_insurance",
                                "health_insurance",
                                "auto_insurance",
                                "property_insurance",
                                "accident_insurance",
                            ],
                            description="Policy type",
                        ),
                        Property(
                            "coverage_amount",
                            "float",
                            min_value=1000.0,
                            max_value=10000000.0,
                            description="Coverage amount",
                        ),
                        Property(
                            "premium",
                            "float",
                            min_value=100.0,
                            max_value=100000.0,
                            description="Premium amount",
                        ),
                        Property("start_date", "date", description="Policy start date"),
                        Property("end_date", "date", description="Policy end date"),
                        Property(
                            "status",
                            "string",
                            is_category=True,
                            allowed_values=[
                                "active",
                                "expired",
                                "cancelled",
                                "suspended",
                            ],
                            description="Policy status",
                        ),
                    ],
                ),
                NodeType(
                    "Claim",
                    [
                        Property(
                            "claim_id",
                            "string",
                            unique=True,
                            indexed=True,
                            description="Unique claim identifier",
                        ),
                        Property(
                            "claim_amount",
                            "float",
                            min_value=100.0,
                            max_value=1000000.0,
                            description="Claim amount",
                        ),
                        Property(
                            "claim_type",
                            "string",
                            is_category=True,
                            allowed_values=["medical", "accident", "property", "death"],
                            description="Claim type",
                        ),
                        Property("incident_date", "date", description="Incident date"),
                        Property(
                            "status",
                            "string",
                            is_category=True,
                            allowed_values=[
                                "pending",
                                "approved",
                                "rejected",
                                "processing",
                            ],
                            description="Claim status",
                        ),
                        Property(
                            "description", "string", description="Claim description"
                        ),
                    ],
                ),
                NodeType(
                    "InsuranceCompany",
                    [
                        Property(
                            "company_id",
                            "string",
                            unique=True,
                            indexed=True,
                            description="Unique insurance company identifier",
                        ),
                        Property(
                            "name", "string", description="Insurance company name"
                        ),
                        Property(
                            "rating",
                            "float",
                            min_value=1.0,
                            max_value=5.0,
                            description="Credit rating",
                        ),
                        Property(
                            "founded_year",
                            "int",
                            min_value=1800,
                            max_value=2024,
                            description="Founded year",
                        ),
                        Property(
                            "total_assets",
                            "float",
                            min_value=1000000.0,
                            max_value=1000000000000.0,
                            description="Total assets",
                        ),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType(
                    "HOLDS",
                    "Policyholder",
                    "Policy",
                    cardinality="1:N",
                    max_connections_per_from=5,
                ),
                RelationshipType(
                    "ISSUES", "InsuranceCompany", "Policy", cardinality="1:N"
                ),
                RelationshipType(
                    "FILES",
                    "Policyholder",
                    "Claim",
                    cardinality="1:N",
                    max_connections_per_from=10,
                ),
                RelationshipType("COVERS", "Policy", "Claim", cardinality="1:N"),
                RelationshipType(
                    "PROCESSES", "InsuranceCompany", "Claim", cardinality="1:N"
                ),
            ],
        )
        schemas.append(insurance_schema)
        return schemas

    def _generate_legal_schemas(self) -> List[DatabaseSchema]:
        schemas = []
        legal_schema = DatabaseSchema(
            name="legal_cases",
            domain="Legal",
            description="Legal Cases System Graph Database Schema",
            node_types=[
                NodeType(
                    "Case",
                    [
                        Property("case_id", "string", unique=True, indexed=True),
                        Property("case_number", "string"),
                        Property("title", "string"),
                        Property("case_type", "string"),
                        Property("status", "string"),
                        Property("filing_date", "date"),
                        Property("judgment_date", "date"),
                        Property("outcome", "string"),
                    ],
                ),
                NodeType(
                    "Person",
                    [
                        Property("person_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("role", "string"),
                        Property("age", "int"),
                        Property("occupation", "string"),
                    ],
                ),
                NodeType(
                    "Law",
                    [
                        Property("law_id", "string", unique=True, indexed=True),
                        Property("law_name", "string"),
                        Property("law_type", "string"),
                        Property("effective_date", "date"),
                        Property("description", "string"),
                    ],
                ),
                NodeType(
                    "Court",
                    [
                        Property("court_id", "string", unique=True, indexed=True),
                        Property("court_name", "string"),
                        Property("jurisdiction", "string"),
                        Property("level", "string"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType("INVOLVES", "Case", "Person", cardinality="N:M"),
                RelationshipType("APPLIES", "Case", "Law", cardinality="N:M"),
                RelationshipType(
                    "HEARD_BY",
                    "Case",
                    "Court",
                    cardinality="N:1",
                    max_connections_per_to=1,
                ),
                RelationshipType(
                    "REPRESENTS",
                    "Person",
                    "Person",
                    cardinality="1:N",
                    max_connections_per_from=5,
                ),
                RelationshipType(
                    "PRECEDES",
                    "Case",
                    "Case",
                    cardinality="1:1",
                    max_connections_per_from=1,
                    max_connections_per_to=1,
                ),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="case_status_consistency",
                    constraint_type="state_consistency",
                    description="Case status must follow legal procedure logic",
                    condition="status IN ('filed', 'in_progress', 'closed') AND (status = 'closed' IMPLIES judgment_date IS NOT NULL)",
                    error_message="Case status inconsistent with judgment date",
                    affected_entities=["Case"],
                ),
                BusinessConstraint(
                    name="case_temporal_consistency",
                    constraint_type="temporal_consistency",
                    description="Case time must follow logical sequence",
                    condition="judgment_date IS NULL OR judgment_date >= filing_date",
                    error_message="Judgment date cannot be earlier than filing date",
                    affected_entities=["Case"],
                ),
                BusinessConstraint(
                    name="lawyer_representation_consistency",
                    constraint_type="business_logic",
                    description="Lawyers can only represent cases within their specialization",
                    condition="person.role = 'lawyer' IMPLIES (case.case_type IN person.specialization)",
                    error_message="Lawyer specialization does not match case type",
                    affected_entities=["Person", "Case"],
                ),
                BusinessConstraint(
                    name="court_jurisdiction_consistency",
                    constraint_type="business_logic",
                    description="Court must have appropriate jurisdiction over the case",
                    condition="court.jurisdiction = case.case_type OR court.level = 'supreme'",
                    error_message="Court lacks jurisdiction over the case",
                    affected_entities=["Court", "Case"],
                ),
                BusinessConstraint(
                    name="case_precedent_consistency",
                    constraint_type="referential_integrity",
                    description="Case precedent relationship must point to closed cases",
                    condition="precedent_case.status = 'closed' AND precedent_case.judgment_date IS NOT NULL",
                    error_message="Precedent case must be closed",
                    affected_entities=["Case"],
                ),
            ],
            cycle_patterns=[],
        )
        schemas.append(legal_schema)
        ip_schema = DatabaseSchema(
            name="intellectual_property",
            domain="Legal",
            description="Intellectual Property System Graph Database Schema",
            node_types=[
                NodeType(
                    "Patent",
                    [
                        Property("patent_id", "string", unique=True, indexed=True),
                        Property("title", "string"),
                        Property("inventor", "string"),
                        Property("filing_date", "date"),
                        Property("grant_date", "date"),
                        Property("status", "string"),
                        Property("category", "string"),
                    ],
                ),
                NodeType(
                    "Trademark",
                    [
                        Property("trademark_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("owner", "string"),
                        Property("registration_date", "date"),
                        Property("class", "string"),
                        Property("status", "string"),
                    ],
                ),
                NodeType(
                    "Copyright",
                    [
                        Property("copyright_id", "string", unique=True, indexed=True),
                        Property("work_title", "string"),
                        Property("author", "string"),
                        Property("creation_date", "date"),
                        Property("registration_date", "date"),
                        Property("work_type", "string"),
                    ],
                ),
                NodeType(
                    "Company",
                    [
                        Property("company_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("industry", "string"),
                        Property("founded_year", "int"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType("OWNS_PATENT", "Company", "Patent", cardinality="1:N"),
                RelationshipType(
                    "OWNS_TRADEMARK", "Company", "Trademark", cardinality="1:N"
                ),
                RelationshipType(
                    "OWNS_COPYRIGHT", "Company", "Copyright", cardinality="1:N"
                ),
                RelationshipType("INFRINGES", "Patent", "Patent", cardinality="N:M"),
                RelationshipType("LICENSES", "Company", "Patent", cardinality="N:M"),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="patent_status_consistency",
                    constraint_type="state_consistency",
                    description="Patent status must follow application process logic",
                    condition="status IN ('pending', 'granted', 'expired', 'rejected') AND (status = 'granted' IMPLIES grant_date IS NOT NULL)",
                    error_message="Patent status inconsistent with grant date",
                    affected_entities=["Patent"],
                ),
                BusinessConstraint(
                    name="patent_temporal_consistency",
                    constraint_type="temporal_consistency",
                    description="Patent time must follow logical sequence",
                    condition="grant_date IS NULL OR grant_date >= filing_date",
                    error_message="Grant date cannot be earlier than filing date",
                    affected_entities=["Patent"],
                ),
                BusinessConstraint(
                    name="trademark_registration_consistency",
                    constraint_type="business_logic",
                    description="Trademark must be registered before use",
                    condition="status = 'active' IMPLIES registration_date IS NOT NULL",
                    error_message="Active trademark must be registered",
                    affected_entities=["Trademark"],
                ),
                BusinessConstraint(
                    name="copyright_protection_consistency",
                    constraint_type="temporal_consistency",
                    description="Copyright protection period must be calculated based on creation date",
                    condition="creation_date IS NOT NULL AND creation_date <= registration_date",
                    error_message="Creation date cannot be later than registration date",
                    affected_entities=["Copyright"],
                ),
                BusinessConstraint(
                    name="patent_infringement_consistency",
                    constraint_type="business_logic",
                    description="Only granted patents can be infringed",
                    condition="infringing_patent.status = 'granted'",
                    error_message="Only granted patents can be infringed",
                    affected_entities=["Patent"],
                ),
            ],
        )
        schemas.append(ip_schema)
        contract_schema = DatabaseSchema(
            name="contract_management",
            domain="Legal",
            description="Contract Management System Graph Database Schema",
            node_types=[
                NodeType(
                    "Contract",
                    [
                        Property("contract_id", "string", unique=True, indexed=True),
                        Property("title", "string"),
                        Property("contract_type", "string"),
                        Property("value", "float"),
                        Property("start_date", "date"),
                        Property("end_date", "date"),
                        Property("status", "string"),
                    ],
                ),
                NodeType(
                    "Party",
                    [
                        Property("party_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("type", "string"),
                        Property("role", "string"),
                        Property("contact_info", "string"),
                    ],
                ),
                NodeType(
                    "Clause",
                    [
                        Property("clause_id", "string", unique=True, indexed=True),
                        Property("clause_text", "string"),
                        Property("clause_type", "string"),
                        Property("importance", "string"),
                    ],
                ),
                NodeType(
                    "Amendment",
                    [
                        Property("amendment_id", "string", unique=True, indexed=True),
                        Property("amendment_date", "date"),
                        Property("description", "string"),
                        Property("status", "string"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType("SIGNS", "Party", "Contract", cardinality="N:M"),
                RelationshipType("CONTAINS", "Contract", "Clause", cardinality="1:N"),
                RelationshipType(
                    "AMENDS",
                    "Amendment",
                    "Contract",
                    cardinality="1:1",
                    max_connections_per_from=1,
                    max_connections_per_to=1,
                ),
                RelationshipType(
                    "REPLACES",
                    "Amendment",
                    "Clause",
                    cardinality="1:1",
                    max_connections_per_from=1,
                    max_connections_per_to=1,
                ),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="contract_status_consistency",
                    constraint_type="state_consistency",
                    description="Contract status must follow business process logic",
                    condition="status IN ('draft', 'active', 'expired', 'terminated', 'suspended') AND (status = 'active' IMPLIES start_date IS NOT NULL)",
                    error_message="Contract status inconsistent with start date",
                    affected_entities=["Contract"],
                ),
                BusinessConstraint(
                    name="contract_temporal_consistency",
                    constraint_type="temporal_consistency",
                    description="Contract time must follow logical sequence",
                    condition="end_date IS NULL OR end_date >= start_date",
                    error_message="Contract end date cannot be earlier than start date",
                    affected_entities=["Contract"],
                ),
                BusinessConstraint(
                    name="contract_value_reasonableness",
                    constraint_type="business_logic",
                    description="Contract value must be positive",
                    condition="value > 0",
                    error_message="Contract value must be positive",
                    affected_entities=["Contract"],
                ),
                BusinessConstraint(
                    name="amendment_temporal_consistency",
                    constraint_type="temporal_consistency",
                    description="Amendment date cannot be earlier than original contract start date",
                    condition="amendment_date >= contract.start_date",
                    error_message="Amendment date cannot be earlier than original contract start date",
                    affected_entities=["Amendment", "Contract"],
                ),
                BusinessConstraint(
                    name="contract_party_consistency",
                    constraint_type="business_logic",
                    description="Contract must have at least two signing parties",
                    condition="COUNT(contract.parties) >= 2",
                    error_message="Contract must have at least two signing parties",
                    affected_entities=["Contract", "Party"],
                ),
            ],
        )
        schemas.append(contract_schema)
        return schemas

    def _generate_sports_schemas(self) -> List[DatabaseSchema]:
        schemas = []
        football_schema = DatabaseSchema(
            name="football_league",
            domain="Sports",
            description="Football League System Graph Database Schema",
            node_types=[
                NodeType(
                    "Player",
                    [
                        Property("player_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("position", "string"),
                        Property("age", "int"),
                        Property("nationality", "string"),
                        Property("market_value", "float"),
                        Property("goals_scored", "int"),
                        Property("assists", "int"),
                    ],
                ),
                NodeType(
                    "Team",
                    [
                        Property("team_id", "string", unique=True, indexed=True),
                        Property("team_name", "string"),
                        Property("city", "string"),
                        Property("founded_year", "int"),
                        Property("stadium", "string"),
                        Property("league_position", "int"),
                    ],
                ),
                NodeType(
                    "Match",
                    [
                        Property("match_id", "string", unique=True, indexed=True),
                        Property("match_date", "date"),
                        Property("home_score", "int"),
                        Property("away_score", "int"),
                        Property("attendance", "int"),
                        Property("weather", "string"),
                    ],
                ),
                NodeType(
                    "League",
                    [
                        Property("league_id", "string", unique=True, indexed=True),
                        Property("league_name", "string"),
                        Property("country", "string"),
                        Property("season", "string"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType(
                    "PLAYS_FOR",
                    "Player",
                    "Team",
                    cardinality="N:1",
                    max_connections_per_to=1,
                ),
                RelationshipType(
                    "PLAYS_IN",
                    "Match",
                    "Team",
                    cardinality="1:2",
                    max_connections_per_from=2,
                ),
                RelationshipType(
                    "BELONGS_TO",
                    "Team",
                    "League",
                    cardinality="N:1",
                    max_connections_per_to=1,
                ),
                RelationshipType("SCORES_IN", "Player", "Match", cardinality="N:M"),
                RelationshipType(
                    "MANAGES",
                    "Person",
                    "Team",
                    cardinality="1:1",
                    max_connections_per_from=1,
                    max_connections_per_to=1,
                ),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="match_result_consistency",
                    constraint_type="business_logic",
                    description="Match result must be logical",
                    condition="home_score >= 0 AND away_score >= 0 AND (home_score != away_score OR home_score = away_score)",
                    error_message="Match scores cannot be negative",
                    affected_entities=["Match"],
                ),
                BusinessConstraint(
                    name="player_age_reasonableness",
                    constraint_type="business_logic",
                    description="Player age must be within reasonable range",
                    condition="age >= 16 AND age <= 45",
                    error_message="Player age must be between 16-45 years",
                    affected_entities=["Player"],
                ),
                BusinessConstraint(
                    name="team_position_consistency",
                    constraint_type="business_logic",
                    description="Team league position must be positive and not exceed total teams",
                    condition="league_position > 0 AND league_position <= 20",
                    error_message="League position must be between 1-20",
                    affected_entities=["Team"],
                ),
                BusinessConstraint(
                    name="player_market_value_reasonableness",
                    constraint_type="business_logic",
                    description="Player market value must be positive",
                    condition="market_value >= 0",
                    error_message="Player market value cannot be negative",
                    affected_entities=["Player"],
                ),
                BusinessConstraint(
                    name="match_temporal_consistency",
                    constraint_type="temporal_consistency",
                    description="Match date cannot be in the future",
                    condition="match_date <= CURRENT_DATE",
                    error_message="Match date cannot be in the future",
                    affected_entities=["Match"],
                ),
            ],
        )
        schemas.append(football_schema)
        olympics_schema = DatabaseSchema(
            name="olympics_system",
            domain="Sports",
            description="Olympics System Graph Database Schema",
            node_types=[
                NodeType(
                    "Athlete",
                    [
                        Property("athlete_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("country", "string"),
                        Property("sport", "string"),
                        Property("age", "int"),
                        Property("gender", "string"),
                    ],
                ),
                NodeType(
                    "Event",
                    [
                        Property("event_id", "string", unique=True, indexed=True),
                        Property("event_name", "string"),
                        Property("sport", "string"),
                        Property("event_date", "date"),
                        Property("venue", "string"),
                    ],
                ),
                NodeType(
                    "Medal",
                    [
                        Property("medal_id", "string", unique=True, indexed=True),
                        Property("medal_type", "string"),
                        Property("event_name", "string"),
                        Property("year", "int"),
                    ],
                ),
                NodeType(
                    "Country",
                    [
                        Property("country_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("code", "string"),
                        Property("population", "int"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType("COMPETES_IN", "Athlete", "Event", cardinality="N:M"),
                RelationshipType("WINS", "Athlete", "Medal", cardinality="N:M"),
                RelationshipType(
                    "REPRESENTS",
                    "Athlete",
                    "Country",
                    cardinality="N:1",
                    max_connections_per_to=1,
                ),
                RelationshipType("HOSTS", "Country", "Event", cardinality="1:N"),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="athlete_age_reasonableness",
                    constraint_type="business_logic",
                    description="Athlete age must be within reasonable range",
                    condition="age >= 14 AND age <= 50",
                    error_message="Athlete age must be between 14-50 years",
                    affected_entities=["Athlete"],
                ),
                BusinessConstraint(
                    name="medal_type_consistency",
                    constraint_type="business_logic",
                    description="Medal type must be valid",
                    condition="medal_type IN ('gold', 'silver', 'bronze')",
                    error_message="Medal type must be gold, silver, or bronze",
                    affected_entities=["Medal"],
                ),
                BusinessConstraint(
                    name="event_temporal_consistency",
                    constraint_type="temporal_consistency",
                    description="Event date cannot be in the future",
                    condition="event_date <= CURRENT_DATE",
                    error_message="Event date cannot be in the future",
                    affected_entities=["Event"],
                ),
                BusinessConstraint(
                    name="athlete_gender_event_consistency",
                    constraint_type="business_logic",
                    description="Athlete gender must match event requirements",
                    condition="(sport IN ('swimming', 'track', 'gymnastics') AND gender IN ('male', 'female')) OR sport NOT IN ('swimming', 'track', 'gymnastics')",
                    error_message="Athlete gender does not match event requirements",
                    affected_entities=["Athlete", "Event"],
                ),
                BusinessConstraint(
                    name="country_code_format_consistency",
                    constraint_type="business_logic",
                    description="Country code must be 3 uppercase letters",
                    condition="LENGTH(code) = 3 AND code = UPPER(code)",
                    error_message="Country code must be 3 uppercase letters",
                    affected_entities=["Country"],
                ),
            ],
        )
        schemas.append(olympics_schema)
        fitness_schema = DatabaseSchema(
            name="fitness_system",
            domain="Sports",
            description="Fitness System Graph Database Schema",
            node_types=[
                NodeType(
                    "Member",
                    [
                        Property("member_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("age", "int"),
                        Property("membership_type", "string"),
                        Property("join_date", "date"),
                        Property("fitness_goal", "string"),
                    ],
                ),
                NodeType(
                    "Exercise",
                    [
                        Property("exercise_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("category", "string"),
                        Property("difficulty", "string"),
                        Property("duration", "int"),
                        Property("calories_burned", "int"),
                    ],
                ),
                NodeType(
                    "Workout",
                    [
                        Property("workout_id", "string", unique=True, indexed=True),
                        Property("date", "date"),
                        Property("duration", "int"),
                        Property("total_calories", "int"),
                        Property("intensity", "string"),
                    ],
                ),
                NodeType(
                    "Trainer",
                    [
                        Property("trainer_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("specialization", "string"),
                        Property("certification", "string"),
                        Property("experience_years", "int"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType("PERFORMS", "Member", "Exercise", cardinality="N:M"),
                RelationshipType("INCLUDES", "Workout", "Exercise", cardinality="1:N"),
                RelationshipType("COMPLETES", "Member", "Workout", cardinality="N:M"),
                RelationshipType(
                    "TRAINS",
                    "Trainer",
                    "Member",
                    cardinality="1:N",
                    max_connections_per_from=10,
                ),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="member_age_reasonableness",
                    constraint_type="business_logic",
                    description="Member age must be within reasonable range",
                    condition="age >= 16 AND age <= 80",
                    error_message="Member age must be between 16-80 years",
                    affected_entities=["Member"],
                ),
                BusinessConstraint(
                    name="workout_duration_reasonableness",
                    constraint_type="business_logic",
                    description="Workout duration must be within reasonable range",
                    condition="duration > 0 AND duration <= 300",
                    error_message="Workout duration must be between 1-300 minutes",
                    affected_entities=["Workout"],
                ),
                BusinessConstraint(
                    name="exercise_calories_reasonableness",
                    constraint_type="business_logic",
                    description="Exercise calories burned must be positive",
                    condition="calories_burned > 0",
                    error_message="Exercise calories burned must be positive",
                    affected_entities=["Exercise"],
                ),
                BusinessConstraint(
                    name="workout_temporal_consistency",
                    constraint_type="temporal_consistency",
                    description="Workout date cannot be in the future",
                    condition="date <= CURRENT_DATE",
                    error_message="Workout date cannot be in the future",
                    affected_entities=["Workout"],
                ),
                BusinessConstraint(
                    name="membership_type_consistency",
                    constraint_type="business_logic",
                    description="Membership type must be valid",
                    condition="membership_type IN ('basic', 'premium', 'vip', 'student', 'senior')",
                    error_message="Membership type must be a valid type",
                    affected_entities=["Member"],
                ),
            ],
        )
        schemas.append(fitness_schema)
        return schemas

    def _generate_education_schemas(self) -> List[DatabaseSchema]:
        schemas = []
        university_schema = DatabaseSchema(
            name="university_system",
            domain="Education",
            description="University System Graph Database Schema",
            node_types=[
                NodeType(
                    "Student",
                    [
                        Property("student_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("age", "int"),
                        Property("major", "string"),
                        Property("gpa", "float"),
                        Property("enrollment_date", "date"),
                        Property("graduation_date", "date"),
                    ],
                ),
                NodeType(
                    "Course",
                    [
                        Property("course_id", "string", unique=True, indexed=True),
                        Property("course_name", "string"),
                        Property("credits", "int"),
                        Property("department", "string"),
                        Property("prerequisites", "string"),
                    ],
                ),
                NodeType(
                    "Professor",
                    [
                        Property("professor_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("department", "string"),
                        Property("specialization", "string"),
                        Property("years_experience", "int"),
                    ],
                ),
                NodeType(
                    "University",
                    [
                        Property("university_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("location", "string"),
                        Property("founded_year", "int"),
                        Property("ranking", "int"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType("ENROLLED_IN", "Student", "Course", cardinality="N:M"),
                RelationshipType(
                    "TEACHES",
                    "Professor",
                    "Course",
                    cardinality="1:N",
                    max_connections_per_from=5,
                ),
                RelationshipType(
                    "ATTENDS",
                    "Student",
                    "University",
                    cardinality="N:1",
                    max_connections_per_to=1,
                ),
                RelationshipType(
                    "WORKS_AT",
                    "Professor",
                    "University",
                    cardinality="N:1",
                    max_connections_per_to=1,
                ),
                RelationshipType(
                    "PREREQUISITE_OF", "Course", "Course", cardinality="N:M"
                ),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="student_age_reasonableness",
                    constraint_type="business_logic",
                    description="Student age must be within reasonable range",
                    condition="age >= 16 AND age <= 30",
                    error_message="Student age must be between 16-30 years",
                    affected_entities=["Student"],
                ),
                BusinessConstraint(
                    name="gpa_reasonableness",
                    constraint_type="business_logic",
                    description="GPA must be between 0-4.0",
                    condition="gpa >= 0.0 AND gpa <= 4.0",
                    error_message="GPA must be between 0-4.0",
                    affected_entities=["Student"],
                ),
                BusinessConstraint(
                    name="course_credits_reasonableness",
                    constraint_type="business_logic",
                    description="Course credits must be positive",
                    condition="credits > 0 AND credits <= 6",
                    error_message="Course credits must be between 1-6",
                    affected_entities=["Course"],
                ),
                BusinessConstraint(
                    name="graduation_temporal_consistency",
                    constraint_type="temporal_consistency",
                    description="Graduation date cannot be earlier than enrollment date",
                    condition="graduation_date IS NULL OR graduation_date >= enrollment_date",
                    error_message="Graduation date cannot be earlier than enrollment date",
                    affected_entities=["Student"],
                ),
                BusinessConstraint(
                    name="professor_experience_reasonableness",
                    constraint_type="business_logic",
                    description="Professor work experience must be positive",
                    condition="years_experience >= 0 AND years_experience <= 50",
                    error_message="Professor work experience must be between 0-50 years",
                    affected_entities=["Professor"],
                ),
                BusinessConstraint(
                    name="university_ranking_reasonableness",
                    constraint_type="business_logic",
                    description="University ranking must be positive",
                    condition="ranking > 0 AND ranking <= 1000",
                    error_message="University ranking must be between 1-1000",
                    affected_entities=["University"],
                ),
            ],
            cycle_patterns=[],
        )
        schemas.append(university_schema)
        online_education_schema = DatabaseSchema(
            name="online_education",
            domain="Education",
            description="Online Education System Graph Database Schema",
            node_types=[
                NodeType(
                    "Learner",
                    [
                        Property("learner_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("age", "int"),
                        Property("learning_goal", "string"),
                        Property("skill_level", "string"),
                        Property("join_date", "date"),
                    ],
                ),
                NodeType(
                    "Course",
                    [
                        Property("course_id", "string", unique=True, indexed=True),
                        Property("title", "string"),
                        Property("category", "string"),
                        Property("difficulty", "string"),
                        Property("duration", "int"),
                        Property("rating", "float"),
                    ],
                ),
                NodeType(
                    "Instructor",
                    [
                        Property("instructor_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("expertise", "string"),
                        Property("rating", "float"),
                        Property("students_count", "int"),
                    ],
                ),
                NodeType(
                    "Platform",
                    [
                        Property("platform_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("type", "string"),
                        Property("founded_year", "int"),
                        Property("user_count", "int"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType("ENROLLS_IN", "Learner", "Course", cardinality="N:M"),
                RelationshipType(
                    "TEACHES",
                    "Instructor",
                    "Course",
                    cardinality="1:N",
                    max_connections_per_from=10,
                ),
                RelationshipType("HOSTS", "Platform", "Course", cardinality="1:N"),
                RelationshipType("REVIEWS", "Learner", "Course", cardinality="N:M"),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="learner_age_reasonableness",
                    constraint_type="business_logic",
                    description="Learner age must be within reasonable range",
                    condition="age >= 12 AND age <= 80",
                    error_message="Learner age must be between 12-80 years",
                    affected_entities=["Learner"],
                ),
                BusinessConstraint(
                    name="course_rating_reasonableness",
                    constraint_type="business_logic",
                    description="Course rating must be between 1-5",
                    condition="rating >= 1.0 AND rating <= 5.0",
                    error_message="Course rating must be between 1-5",
                    affected_entities=["Course"],
                ),
                BusinessConstraint(
                    name="course_duration_reasonableness",
                    constraint_type="business_logic",
                    description="Course duration must be positive",
                    condition="duration > 0 AND duration <= 1000",
                    error_message="Course duration must be between 1-1000 hours",
                    affected_entities=["Course"],
                ),
                BusinessConstraint(
                    name="instructor_rating_reasonableness",
                    constraint_type="business_logic",
                    description="Instructor rating must be between 1-5",
                    condition="rating >= 1.0 AND rating <= 5.0",
                    error_message="Instructor rating must be between 1-5",
                    affected_entities=["Instructor"],
                ),
                BusinessConstraint(
                    name="platform_user_count_reasonableness",
                    constraint_type="business_logic",
                    description="Platform user count must be positive",
                    condition="user_count >= 0",
                    error_message="Platform user count cannot be negative",
                    affected_entities=["Platform"],
                ),
                BusinessConstraint(
                    name="skill_level_consistency",
                    constraint_type="business_logic",
                    description="Skill level must be valid",
                    condition="skill_level IN ('beginner', 'intermediate', 'advanced', 'expert')",
                    error_message="Skill level must be a valid level",
                    affected_entities=["Learner"],
                ),
            ],
        )
        schemas.append(online_education_schema)
        research_schema = DatabaseSchema(
            name="research_projects",
            domain="Education",
            description="Research Projects System Graph Database Schema",
            node_types=[
                NodeType(
                    "Researcher",
                    [
                        Property("researcher_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("field", "string"),
                        Property("institution", "string"),
                        Property("publications", "int"),
                        Property("h_index", "int"),
                    ],
                ),
                NodeType(
                    "Project",
                    [
                        Property("project_id", "string", unique=True, indexed=True),
                        Property("title", "string"),
                        Property("field", "string"),
                        Property("start_date", "date"),
                        Property("end_date", "date"),
                        Property("budget", "float"),
                        Property("status", "string"),
                    ],
                ),
                NodeType(
                    "Publication",
                    [
                        Property("publication_id", "string", unique=True, indexed=True),
                        Property("title", "string"),
                        Property("journal", "string"),
                        Property("publication_date", "date"),
                        Property("impact_factor", "float"),
                        Property("citations", "int"),
                    ],
                ),
                NodeType(
                    "Funding",
                    [
                        Property("funding_id", "string", unique=True, indexed=True),
                        Property("source", "string"),
                        Property("amount", "float"),
                        Property("grant_type", "string"),
                        Property("duration", "int"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType(
                    "LEADS",
                    "Researcher",
                    "Project",
                    cardinality="1:N",
                    max_connections_per_from=3,
                ),
                RelationshipType(
                    "COLLABORATES_ON", "Researcher", "Project", cardinality="N:M"
                ),
                RelationshipType(
                    "PUBLISHES", "Researcher", "Publication", cardinality="N:M"
                ),
                RelationshipType("FUNDS", "Funding", "Project", cardinality="1:N"),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="project_budget_reasonableness",
                    constraint_type="business_logic",
                    description="Project budget must be positive",
                    condition="budget > 0",
                    error_message="Project budget must be positive",
                    affected_entities=["Project"],
                ),
                BusinessConstraint(
                    name="project_temporal_consistency",
                    constraint_type="temporal_consistency",
                    description="Project end date cannot be earlier than start date",
                    condition="end_date IS NULL OR end_date >= start_date",
                    error_message="Project end date cannot be earlier than start date",
                    affected_entities=["Project"],
                ),
                BusinessConstraint(
                    name="researcher_h_index_reasonableness",
                    constraint_type="business_logic",
                    description="Researcher h-index must be non-negative",
                    condition="h_index >= 0 AND h_index <= 200",
                    error_message="Researcher h-index must be between 0-200",
                    affected_entities=["Researcher"],
                ),
                BusinessConstraint(
                    name="publication_impact_factor_reasonableness",
                    constraint_type="business_logic",
                    description="Publication impact factor must be positive",
                    condition="impact_factor > 0 AND impact_factor <= 100",
                    error_message="Publication impact factor must be between 0-100",
                    affected_entities=["Publication"],
                ),
                BusinessConstraint(
                    name="funding_amount_reasonableness",
                    constraint_type="business_logic",
                    description="Funding amount must be positive",
                    condition="amount > 0",
                    error_message="Funding amount must be positive",
                    affected_entities=["Funding"],
                ),
                BusinessConstraint(
                    name="project_status_consistency",
                    constraint_type="state_consistency",
                    description="Project status must follow research process logic",
                    condition="status IN ('planning', 'active', 'completed', 'cancelled', 'suspended')",
                    error_message="Project status must be a valid status",
                    affected_entities=["Project"],
                ),
            ],
        )
        schemas.append(research_schema)
        return schemas

    def _generate_social_schemas(self) -> List[DatabaseSchema]:
        schemas = []
        social_schema = DatabaseSchema(
            name="social_network",
            domain="Social",
            description="Social Network System Graph Database Schema",
            node_types=[
                NodeType(
                    "User",
                    [
                        Property("user_id", "string", unique=True, indexed=True),
                        Property("username", "string", unique=True),
                        Property("email", "string"),
                        Property("age", "int"),
                        Property("location", "string"),
                        Property("join_date", "date"),
                        Property("last_active", "datetime"),
                    ],
                ),
                NodeType(
                    "Post",
                    [
                        Property("post_id", "string", unique=True, indexed=True),
                        Property("content", "string"),
                        Property("post_type", "string"),
                        Property("timestamp", "datetime"),
                        Property("likes_count", "int"),
                        Property("shares_count", "int"),
                    ],
                ),
                NodeType(
                    "Group",
                    [
                        Property("group_id", "string", unique=True, indexed=True),
                        Property("group_name", "string"),
                        Property("description", "string"),
                        Property("member_count", "int"),
                        Property("created_date", "date"),
                    ],
                ),
                NodeType(
                    "Event",
                    [
                        Property("event_id", "string", unique=True, indexed=True),
                        Property("event_name", "string"),
                        Property("description", "string"),
                        Property("event_date", "datetime"),
                        Property("location", "string"),
                        Property("attendee_count", "int"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType(
                    "FRIENDS_WITH",
                    "User",
                    "User",
                    properties=[
                        Property(
                            "friendship_strength",
                            "string",
                            required=True,
                            allowed_values=[
                                "close",
                                "casual",
                                "acquaintance",
                                "colleague",
                            ],
                            is_category=True,
                            description="Strength of friendship",
                        ),
                        Property(
                            "friendship_duration",
                            "int",
                            required=True,
                            min_value=0,
                            max_value=50,
                            description="Years of friendship",
                        ),
                    ],
                    cardinality="N:M",
                ),
                RelationshipType(
                    "CREATES",
                    "User",
                    "Post",
                    cardinality="1:N",
                    max_connections_per_from=100,
                ),
                RelationshipType("LIKES", "User", "Post", cardinality="N:M"),
                RelationshipType("JOINS", "User", "Group", cardinality="N:M"),
                RelationshipType("ATTENDS", "User", "Event", cardinality="N:M"),
                RelationshipType("COMMENTS_ON", "User", "Post", cardinality="N:M"),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="user_age_reasonableness",
                    constraint_type="business_logic",
                    description="User age must be within reasonable range",
                    condition="age >= 13 AND age <= 100",
                    error_message="User age must be between 13-100 years",
                    affected_entities=["User"],
                ),
                BusinessConstraint(
                    name="post_likes_reasonableness",
                    constraint_type="business_logic",
                    description="Post likes count must be non-negative",
                    condition="likes_count >= 0",
                    error_message="Post likes count cannot be negative",
                    affected_entities=["Post"],
                ),
                BusinessConstraint(
                    name="post_shares_reasonableness",
                    constraint_type="business_logic",
                    description="Post shares count must be non-negative",
                    condition="shares_count >= 0",
                    error_message="Post shares count cannot be negative",
                    affected_entities=["Post"],
                ),
                BusinessConstraint(
                    name="group_member_count_reasonableness",
                    constraint_type="business_logic",
                    description="Group member count must be non-negative",
                    condition="member_count >= 0",
                    error_message="Group member count cannot be negative",
                    affected_entities=["Group"],
                ),
                BusinessConstraint(
                    name="event_attendee_count_reasonableness",
                    constraint_type="business_logic",
                    description="Event attendee count must be non-negative",
                    condition="attendee_count >= 0",
                    error_message="Event attendee count cannot be negative",
                    affected_entities=["Event"],
                ),
                BusinessConstraint(
                    name="user_activity_temporal_consistency",
                    constraint_type="temporal_consistency",
                    description="User last active time cannot be earlier than join date",
                    condition="last_active >= join_date",
                    error_message="User last active time cannot be earlier than join date",
                    affected_entities=["User"],
                ),
            ],
            cycle_patterns=[
                CyclePattern(
                    id="social_cycle_1",
                    name="friendship_cycle",
                    description="User-Friends-User cycle pattern",
                    cycle_path=[
                        "User",
                        "FRIENDS_WITH",
                        "User",
                        "FRIENDS_WITH",
                        "User",
                        "FRIENDS_WITH",
                        "User",
                    ],
                    cycle_length=7,
                    is_valid=True,
                    explanation="Users can be friends with each other, forming friendship cycles",
                    business_logic="Follows social network logic, users can have mutual friends forming friendship triangles",
                    node_types_involved=["User"],
                    relationship_types_involved=["FRIENDS_WITH"],
                    instance_cycle_description="User A is friends with User B, User B is friends with User C, User C is friends with User A",
                    example_cycle={
                        "description": "Three users form a friendship triangle",
                        "cycle_instances": [
                            {"type": "User", "id": "User_001", "username": "alice"},
                            {
                                "type": "FRIENDS_WITH",
                                "id": "FRIENDS_WITH_001",
                                "from": "User_001",
                                "to": "User_002",
                            },
                            {"type": "User", "id": "User_002", "username": "bob"},
                            {
                                "type": "FRIENDS_WITH",
                                "id": "FRIENDS_WITH_002",
                                "from": "User_002",
                                "to": "User_003",
                            },
                            {"type": "User", "id": "User_003", "username": "charlie"},
                            {
                                "type": "FRIENDS_WITH",
                                "id": "FRIENDS_WITH_003",
                                "from": "User_003",
                                "to": "User_001",
                            },
                        ],
                    },
                    constraints={
                        "min_cycle_length": 3,
                        "max_cycle_length": 10,
                        "business_rules": [
                            "Friendship must be mutual",
                            "Users must be active to maintain friendships",
                        ],
                    },
                )
            ],
        )
        schemas.append(social_schema)
        dating_schema = DatabaseSchema(
            name="dating_system",
            domain="Social",
            description="Dating System Graph Database Schema",
            node_types=[
                NodeType(
                    "Profile",
                    [
                        Property("profile_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("age", "int"),
                        Property("gender", "string"),
                        Property("location", "string"),
                        Property("interests", "string"),
                        Property("bio", "string"),
                    ],
                ),
                NodeType(
                    "Match",
                    [
                        Property("match_id", "string", unique=True, indexed=True),
                        Property("match_date", "date"),
                        Property("compatibility_score", "float"),
                        Property("status", "string"),
                    ],
                ),
                NodeType(
                    "Message",
                    [
                        Property("message_id", "string", unique=True, indexed=True),
                        Property("content", "string"),
                        Property("timestamp", "datetime"),
                        Property("message_type", "string"),
                    ],
                ),
                NodeType(
                    "Date",
                    [
                        Property("date_id", "string", unique=True, indexed=True),
                        Property("date_time", "datetime"),
                        Property("location", "string"),
                        Property("activity", "string"),
                        Property("status", "string"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType(
                    "MATCHES_WITH", "Profile", "Profile", cardinality="N:M"
                ),
                RelationshipType("SENDS", "Profile", "Message", cardinality="1:N"),
                RelationshipType("PLANS", "Profile", "Date", cardinality="N:M"),
                RelationshipType(
                    "RESULTS_FROM",
                    "Date",
                    "Match",
                    cardinality="1:1",
                    max_connections_per_from=1,
                    max_connections_per_to=1,
                ),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="profile_age_reasonableness",
                    constraint_type="business_logic",
                    description="User age must be within reasonable range",
                    condition="age >= 18 AND age <= 80",
                    error_message="User age must be between 18-80 years",
                    affected_entities=["Profile"],
                ),
                BusinessConstraint(
                    name="match_compatibility_reasonableness",
                    constraint_type="business_logic",
                    description="Match compatibility score must be between 0-1",
                    condition="compatibility_score >= 0.0 AND compatibility_score <= 1.0",
                    error_message="Match compatibility score must be between 0-1",
                    affected_entities=["Match"],
                ),
                BusinessConstraint(
                    name="date_temporal_consistency",
                    constraint_type="temporal_consistency",
                    description="Date time cannot be in the past",
                    condition="date_time >= NOW()",
                    error_message="Date time cannot be in the past",
                    affected_entities=["Date"],
                ),
                BusinessConstraint(
                    name="match_status_consistency",
                    constraint_type="state_consistency",
                    description="Match status must be valid",
                    condition="status IN ('pending', 'accepted', 'rejected', 'expired')",
                    error_message="Match status must be a valid status",
                    affected_entities=["Match"],
                ),
            ],
            cycle_patterns=[
                CyclePattern(
                    id="dating_cycle_1",
                    name="profile_match_cycle",
                    description="Profile-Match-Profile cycle pattern",
                    cycle_path=[
                        "Profile",
                        "MATCHES_WITH",
                        "Profile",
                        "MATCHES_WITH",
                        "Profile",
                        "MATCHES_WITH",
                        "Profile",
                    ],
                    cycle_length=7,
                    is_valid=True,
                    explanation="Profiles can match with each other, forming a cycle of matching relationships",
                    business_logic="Follows dating system logic, users can match with multiple profiles forming cycles",
                    node_types_involved=["Profile"],
                    relationship_types_involved=["MATCHES_WITH"],
                    instance_cycle_description="Multiple profiles match with each other, eventually forming a cycle",
                    example_cycle={
                        "description": "Three profiles form a match cycle",
                        "cycle_instances": [
                            {"type": "Profile", "id": "Profile_001", "name": "Alice"},
                            {
                                "type": "MATCHES_WITH",
                                "id": "MATCHES_WITH_001",
                                "from": "Profile_001",
                                "to": "Profile_002",
                            },
                            {"type": "Profile", "id": "Profile_002", "name": "Bob"},
                            {
                                "type": "MATCHES_WITH",
                                "id": "MATCHES_WITH_002",
                                "from": "Profile_002",
                                "to": "Profile_003",
                            },
                            {"type": "Profile", "id": "Profile_003", "name": "Charlie"},
                            {
                                "type": "MATCHES_WITH",
                                "id": "MATCHES_WITH_003",
                                "from": "Profile_003",
                                "to": "Profile_001",
                            },
                        ],
                    },
                    constraints={
                        "min_cycle_length": 3,
                        "max_cycle_length": 10,
                        "business_rules": [
                            "Match relationships can form cycles in dating networks",
                            "Profiles must meet matching criteria",
                        ],
                    },
                )
            ],
        )
        schemas.append(dating_schema)
        professional_schema = DatabaseSchema(
            name="professional_network",
            domain="Social",
            description="Professional Network System Graph Database Schema",
            node_types=[
                NodeType(
                    "Professional",
                    [
                        Property(
                            "professional_id", "string", unique=True, indexed=True
                        ),
                        Property("name", "string"),
                        Property("title", "string"),
                        Property("company", "string"),
                        Property("industry", "string"),
                        Property("experience_years", "int"),
                        Property("skills", "string"),
                    ],
                ),
                NodeType(
                    "Company",
                    [
                        Property("company_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("industry", "string"),
                        Property("size", "string"),
                        Property("location", "string"),
                        Property("founded_year", "int"),
                    ],
                ),
                NodeType(
                    "Job",
                    [
                        Property("job_id", "string", unique=True, indexed=True),
                        Property("title", "string"),
                        Property("description", "string"),
                        Property("salary_range", "string"),
                        Property("location", "string"),
                        Property("posted_date", "date"),
                    ],
                ),
                NodeType(
                    "Skill",
                    [
                        Property("skill_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("category", "string"),
                        Property("demand_level", "string"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType(
                    "CONNECTS_WITH", "Professional", "Professional", cardinality="N:M"
                ),
                RelationshipType(
                    "WORKS_AT",
                    "Professional",
                    "Company",
                    cardinality="N:1",
                    max_connections_per_to=1,
                ),
                RelationshipType("POSTS", "Company", "Job", cardinality="1:N"),
                RelationshipType(
                    "HAS_SKILL", "Professional", "Skill", cardinality="N:M"
                ),
                RelationshipType("REQUIRES", "Job", "Skill", cardinality="N:M"),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="professional_experience_reasonableness",
                    constraint_type="business_logic",
                    description="Work experience must be non-negative",
                    condition="experience_years >= 0 AND experience_years <= 50",
                    error_message="Work experience must be between 0-50 years",
                    affected_entities=["Professional"],
                ),
                BusinessConstraint(
                    name="company_founded_year_reasonableness",
                    constraint_type="business_logic",
                    description="Company founded year must be within reasonable range",
                    condition="founded_year >= 1800 AND founded_year <= 2024",
                    error_message="Company founded year must be between 1800-2024",
                    affected_entities=["Company"],
                ),
                BusinessConstraint(
                    name="job_posted_date_consistency",
                    constraint_type="temporal_consistency",
                    description="Job posted date cannot be in the future",
                    condition="posted_date <= CURRENT_DATE",
                    error_message="Job posted date cannot be in the future",
                    affected_entities=["Job"],
                ),
                BusinessConstraint(
                    name="skill_demand_level_consistency",
                    constraint_type="business_logic",
                    description="Skill demand level must be valid",
                    condition="demand_level IN ('low', 'medium', 'high', 'critical')",
                    error_message="Skill demand level must be a valid level",
                    affected_entities=["Skill"],
                ),
            ],
        )
        schemas.append(professional_schema)
        return schemas

    def _generate_healthcare_schemas(self) -> List[DatabaseSchema]:
        schemas = []
        hospital_schema = DatabaseSchema(
            name="hospital_system",
            domain="Healthcare",
            description="Hospital System Graph Database Schema",
            node_types=[
                NodeType(
                    "Patient",
                    [
                        Property("patient_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("age", "int"),
                        Property("gender", "string"),
                        Property("blood_type", "string"),
                        Property("medical_history", "string"),
                        Property("admission_date", "date"),
                    ],
                ),
                NodeType(
                    "Doctor",
                    [
                        Property("doctor_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("specialization", "string"),
                        Property("years_experience", "int"),
                        Property("license_number", "string"),
                    ],
                ),
                NodeType(
                    "Treatment",
                    [
                        Property("treatment_id", "string", unique=True, indexed=True),
                        Property("treatment_name", "string"),
                        Property("treatment_type", "string"),
                        Property("duration", "int"),
                        Property("cost", "float"),
                    ],
                ),
                NodeType(
                    "Hospital",
                    [
                        Property("hospital_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("location", "string"),
                        Property("capacity", "int"),
                        Property("specialties", "string"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType("TREATED_BY", "Patient", "Doctor", cardinality="N:M"),
                RelationshipType("RECEIVES", "Patient", "Treatment", cardinality="N:M"),
                RelationshipType(
                    "WORKS_AT",
                    "Doctor",
                    "Hospital",
                    cardinality="N:1",
                    max_connections_per_to=1,
                ),
                RelationshipType(
                    "ADMITTED_TO",
                    "Patient",
                    "Hospital",
                    cardinality="N:1",
                    max_connections_per_to=1,
                ),
                RelationshipType(
                    "SPECIALIZES_IN", "Doctor", "Treatment", cardinality="N:M"
                ),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="patient_age_reasonableness",
                    constraint_type="business_logic",
                    description="Patient age must be within reasonable range",
                    condition="age >= 0 AND age <= 120",
                    error_message="Patient age must be between 0-120 years",
                    affected_entities=["Patient"],
                ),
                BusinessConstraint(
                    name="doctor_experience_reasonableness",
                    constraint_type="business_logic",
                    description="Doctor work experience must be positive",
                    condition="years_experience >= 0 AND years_experience <= 50",
                    error_message="Doctor work experience must be between 0-50 years",
                    affected_entities=["Doctor"],
                ),
                BusinessConstraint(
                    name="treatment_cost_reasonableness",
                    constraint_type="business_logic",
                    description="Treatment cost must be positive",
                    condition="cost > 0",
                    error_message="Treatment cost must be positive",
                    affected_entities=["Treatment"],
                ),
                BusinessConstraint(
                    name="hospital_capacity_reasonableness",
                    constraint_type="business_logic",
                    description="Hospital capacity must be positive",
                    condition="capacity > 0",
                    error_message="Hospital capacity must be positive",
                    affected_entities=["Hospital"],
                ),
                BusinessConstraint(
                    name="patient_admission_temporal_consistency",
                    constraint_type="temporal_consistency",
                    description="Patient admission date cannot be in the future",
                    condition="admission_date <= CURRENT_DATE",
                    error_message="Patient admission date cannot be in the future",
                    affected_entities=["Patient"],
                ),
            ],
        )
        schemas.append(hospital_schema)
        drug_research_schema = DatabaseSchema(
            name="drug_research",
            domain="Healthcare",
            description="Drug Research System Graph Database Schema",
            node_types=[
                NodeType(
                    "Drug",
                    [
                        Property("drug_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("type", "string"),
                        Property("mechanism", "string"),
                        Property("dosage", "string"),
                        Property("side_effects", "string"),
                    ],
                ),
                NodeType(
                    "ClinicalTrial",
                    [
                        Property("trial_id", "string", unique=True, indexed=True),
                        Property("phase", "string"),
                        Property("start_date", "date"),
                        Property("end_date", "date"),
                        Property("participants", "int"),
                        Property("success_rate", "float"),
                    ],
                ),
                NodeType(
                    "Disease",
                    [
                        Property("disease_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("category", "string"),
                        Property("severity", "string"),
                        Property("prevalence", "float"),
                    ],
                ),
                NodeType(
                    "ResearchCenter",
                    [
                        Property("center_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("location", "string"),
                        Property("specialization", "string"),
                        Property("funding", "float"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType("TREATS", "Drug", "Disease", cardinality="N:M"),
                RelationshipType(
                    "TESTED_IN", "Drug", "ClinicalTrial", cardinality="N:M"
                ),
                RelationshipType(
                    "CONDUCTS", "ResearchCenter", "ClinicalTrial", cardinality="1:N"
                ),
                RelationshipType(
                    "TARGETS",
                    "ClinicalTrial",
                    "Disease",
                    cardinality="1:1",
                    max_connections_per_from=1,
                    max_connections_per_to=1,
                ),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="clinical_trial_participants_reasonableness",
                    constraint_type="business_logic",
                    description="Clinical trial participants count must be positive",
                    condition="participants > 0",
                    error_message="Clinical trial participants count must be positive",
                    affected_entities=["ClinicalTrial"],
                ),
                BusinessConstraint(
                    name="clinical_trial_success_rate_reasonableness",
                    constraint_type="business_logic",
                    description="Clinical trial success rate must be between 0-1",
                    condition="success_rate >= 0.0 AND success_rate <= 1.0",
                    error_message="Clinical trial success rate must be between 0-1",
                    affected_entities=["ClinicalTrial"],
                ),
                BusinessConstraint(
                    name="disease_prevalence_reasonableness",
                    constraint_type="business_logic",
                    description="Disease prevalence must be between 0-1",
                    condition="prevalence >= 0.0 AND prevalence <= 1.0",
                    error_message="Disease prevalence must be between 0-1",
                    affected_entities=["Disease"],
                ),
                BusinessConstraint(
                    name="research_center_funding_reasonableness",
                    constraint_type="business_logic",
                    description="Research center funding must be positive",
                    condition="funding > 0",
                    error_message="Research center funding must be positive",
                    affected_entities=["ResearchCenter"],
                ),
                BusinessConstraint(
                    name="clinical_trial_temporal_consistency",
                    constraint_type="temporal_consistency",
                    description="Clinical trial end date cannot be earlier than start date",
                    condition="end_date >= start_date",
                    error_message="Clinical trial end date cannot be earlier than start date",
                    affected_entities=["ClinicalTrial"],
                ),
            ],
        )
        schemas.append(drug_research_schema)
        health_monitoring_schema = DatabaseSchema(
            name="health_monitoring",
            domain="Healthcare",
            description="Health Monitoring System Graph Database Schema",
            node_types=[
                NodeType(
                    "User",
                    [
                        Property("user_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("age", "int"),
                        Property("gender", "string"),
                        Property("height", "float"),
                        Property("weight", "float"),
                        Property("fitness_goal", "string"),
                    ],
                ),
                NodeType(
                    "Device",
                    [
                        Property("device_id", "string", unique=True, indexed=True),
                        Property("type", "string"),
                        Property("model", "string"),
                        Property("battery_level", "int"),
                        Property("last_sync", "datetime"),
                    ],
                ),
                NodeType(
                    "HealthMetric",
                    [
                        Property("metric_id", "string", unique=True, indexed=True),
                        Property("metric_type", "string"),
                        Property("value", "float"),
                        Property("unit", "string"),
                        Property("timestamp", "datetime"),
                    ],
                ),
                NodeType(
                    "Alert",
                    [
                        Property("alert_id", "string", unique=True, indexed=True),
                        Property("alert_type", "string"),
                        Property("severity", "string"),
                        Property("message", "string"),
                        Property("timestamp", "datetime"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType("USES", "User", "Device", cardinality="N:M"),
                RelationshipType(
                    "COLLECTS", "Device", "HealthMetric", cardinality="1:N"
                ),
                RelationshipType(
                    "TRIGGERS", "HealthMetric", "Alert", cardinality="N:M"
                ),
                RelationshipType("RECEIVES", "User", "Alert", cardinality="N:M"),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="user_physical_measurements_reasonableness",
                    constraint_type="business_logic",
                    description="User height and weight must be within reasonable range",
                    condition="height > 0 AND height <= 250 AND weight > 0 AND weight <= 300",
                    error_message="User height and weight must be within reasonable range",
                    affected_entities=["User"],
                ),
                BusinessConstraint(
                    name="device_battery_level_reasonableness",
                    constraint_type="business_logic",
                    description="Device battery level must be between 0-100",
                    condition="battery_level >= 0 AND battery_level <= 100",
                    error_message="Device battery level must be between 0-100",
                    affected_entities=["Device"],
                ),
                BusinessConstraint(
                    name="health_metric_value_reasonableness",
                    constraint_type="business_logic",
                    description="Health metric value must be positive",
                    condition="value > 0",
                    error_message="Health metric value must be positive",
                    affected_entities=["HealthMetric"],
                ),
                BusinessConstraint(
                    name="alert_severity_consistency",
                    constraint_type="business_logic",
                    description="Alert severity must be valid",
                    condition="severity IN ('low', 'medium', 'high', 'critical')",
                    error_message="Alert severity must be a valid level",
                    affected_entities=["Alert"],
                ),
                BusinessConstraint(
                    name="device_sync_temporal_consistency",
                    constraint_type="temporal_consistency",
                    description="Device last sync time cannot be in the future",
                    condition="last_sync <= NOW()",
                    error_message="Device last sync time cannot be in the future",
                    affected_entities=["Device"],
                ),
            ],
        )
        schemas.append(health_monitoring_schema)
        return schemas

    def _generate_ecommerce_schemas(self) -> List[DatabaseSchema]:
        schemas = []
        ecommerce_schema = DatabaseSchema(
            name="ecommerce_system",
            domain="E-commerce",
            description="E-commerce System Graph Database Schema",
            node_types=[
                NodeType(
                    "Customer",
                    [
                        Property("customer_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("email", "string"),
                        Property("phone", "string"),
                        Property("address", "string"),
                        Property("registration_date", "date"),
                        Property("total_orders", "int"),
                    ],
                ),
                NodeType(
                    "Product",
                    [
                        Property("product_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("category", "string"),
                        Property("price", "float"),
                        Property("stock", "int"),
                        Property("rating", "float"),
                        Property("description", "string"),
                    ],
                ),
                NodeType(
                    "Order",
                    [
                        Property("order_id", "string", unique=True, indexed=True),
                        Property("order_date", "datetime"),
                        Property("total_amount", "float"),
                        Property("status", "string"),
                        Property("shipping_address", "string"),
                    ],
                ),
                NodeType(
                    "Seller",
                    [
                        Property("seller_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("rating", "float"),
                        Property("location", "string"),
                        Property("join_date", "date"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType("PLACES", "Customer", "Order", cardinality="1:N"),
                RelationshipType("CONTAINS", "Order", "Product", cardinality="N:M"),
                RelationshipType("SELLS", "Seller", "Product", cardinality="1:N"),
                RelationshipType(
                    "REVIEWS",
                    "Customer",
                    "Product",
                    properties=[
                        Property(
                            "review_helpfulness",
                            "int",
                            required=True,
                            min_value=0,
                            max_value=100,
                            description="How helpful this review is rated by other customers",
                        ),
                        Property(
                            "review_verified",
                            "boolean",
                            required=True,
                            description="Whether this is a verified purchase review",
                        ),
                    ],
                    cardinality="N:M",
                ),
                RelationshipType("SIMILAR_TO", "Product", "Product", cardinality="N:M"),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="product_price_reasonableness",
                    constraint_type="business_logic",
                    description="Product price must be positive",
                    condition="price > 0",
                    error_message="Product price must be positive",
                    affected_entities=["Product"],
                ),
                BusinessConstraint(
                    name="product_stock_reasonableness",
                    constraint_type="business_logic",
                    description="Product stock must be non-negative",
                    condition="stock >= 0",
                    error_message="Product stock cannot be negative",
                    affected_entities=["Product"],
                ),
                BusinessConstraint(
                    name="product_rating_reasonableness",
                    constraint_type="business_logic",
                    description="Product rating must be between 1-5",
                    condition="rating >= 1.0 AND rating <= 5.0",
                    error_message="Product rating must be between 1-5",
                    affected_entities=["Product"],
                ),
                BusinessConstraint(
                    name="order_total_amount_reasonableness",
                    constraint_type="business_logic",
                    description="Order total amount must be positive",
                    condition="total_amount > 0",
                    error_message="Order total amount must be positive",
                    affected_entities=["Order"],
                ),
                BusinessConstraint(
                    name="seller_rating_reasonableness",
                    constraint_type="business_logic",
                    description="Seller rating must be between 1-5",
                    condition="rating >= 1.0 AND rating <= 5.0",
                    error_message="Seller rating must be between 1-5",
                    affected_entities=["Seller"],
                ),
                BusinessConstraint(
                    name="order_status_consistency",
                    constraint_type="state_consistency",
                    description="Order status must be valid",
                    condition="status IN ('pending', 'confirmed', 'shipped', 'delivered', 'cancelled', 'returned')",
                    error_message="Order status must be a valid status",
                    affected_entities=["Order"],
                ),
            ],
            cycle_patterns=[
                CyclePattern(
                    id="ecommerce_cycle_1",
                    name="product_similarity_cycle",
                    description="Product-Similarity-Product cycle pattern",
                    cycle_path=[
                        "Product",
                        "SIMILAR_TO",
                        "Product",
                        "SIMILAR_TO",
                        "Product",
                        "SIMILAR_TO",
                        "Product",
                    ],
                    cycle_length=7,
                    is_valid=True,
                    explanation="Products can be similar to each other, forming a cycle of similarity relationships",
                    business_logic="Follows ecommerce logic, products can have similar relationships forming cycles",
                    node_types_involved=["Product"],
                    relationship_types_involved=["SIMILAR_TO"],
                    instance_cycle_description="Multiple products are similar to each other, eventually forming a cycle",
                    example_cycle={
                        "description": "Three products form a similarity cycle",
                        "cycle_instances": [
                            {
                                "type": "Product",
                                "id": "Product_001",
                                "name": "Product A",
                            },
                            {
                                "type": "SIMILAR_TO",
                                "id": "SIMILAR_TO_001",
                                "from": "Product_001",
                                "to": "Product_002",
                            },
                            {
                                "type": "Product",
                                "id": "Product_002",
                                "name": "Product B",
                            },
                            {
                                "type": "SIMILAR_TO",
                                "id": "SIMILAR_TO_002",
                                "from": "Product_002",
                                "to": "Product_003",
                            },
                            {
                                "type": "Product",
                                "id": "Product_003",
                                "name": "Product C",
                            },
                            {
                                "type": "SIMILAR_TO",
                                "id": "SIMILAR_TO_003",
                                "from": "Product_003",
                                "to": "Product_001",
                            },
                        ],
                    },
                    constraints={
                        "min_cycle_length": 3,
                        "max_cycle_length": 10,
                        "business_rules": [
                            "Product similarity relationships can form cycles",
                            "Similar products should have comparable features",
                        ],
                    },
                )
            ],
        )
        schemas.append(ecommerce_schema)
        supply_chain_schema = DatabaseSchema(
            name="supply_chain",
            domain="E-commerce",
            description="Supply Chain System Graph Database Schema",
            node_types=[
                NodeType(
                    "Supplier",
                    [
                        Property("supplier_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("location", "string"),
                        Property("rating", "float"),
                        Property("capacity", "int"),
                        Property("lead_time", "int"),
                    ],
                ),
                NodeType(
                    "Warehouse",
                    [
                        Property("warehouse_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("location", "string"),
                        Property("capacity", "int"),
                        Property("current_stock", "int"),
                        Property("operating_hours", "string"),
                    ],
                ),
                NodeType(
                    "Shipment",
                    [
                        Property("shipment_id", "string", unique=True, indexed=True),
                        Property("origin", "string"),
                        Property("destination", "string"),
                        Property("ship_date", "date"),
                        Property("delivery_date", "date"),
                        Property("status", "string"),
                    ],
                ),
                NodeType(
                    "Inventory",
                    [
                        Property("inventory_id", "string", unique=True, indexed=True),
                        Property("product_name", "string"),
                        Property("quantity", "int"),
                        Property("unit_cost", "float"),
                        Property("last_updated", "datetime"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType(
                    "SUPPLIES", "Supplier", "Inventory", cardinality="1:N"
                ),
                RelationshipType("STORES", "Warehouse", "Inventory", cardinality="1:N"),
                RelationshipType(
                    "TRANSPORTS", "Shipment", "Inventory", cardinality="N:M"
                ),
                RelationshipType(
                    "RECEIVES_FROM", "Warehouse", "Supplier", cardinality="N:M"
                ),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="supplier_rating_reasonableness",
                    constraint_type="business_logic",
                    description="Supplier rating must be between 1-5",
                    condition="rating >= 1.0 AND rating <= 5.0",
                    error_message="Supplier rating must be between 1-5",
                    affected_entities=["Supplier"],
                ),
                BusinessConstraint(
                    name="supplier_capacity_reasonableness",
                    constraint_type="business_logic",
                    description="Supplier capacity must be positive",
                    condition="capacity > 0",
                    error_message="Supplier capacity must be positive",
                    affected_entities=["Supplier"],
                ),
                BusinessConstraint(
                    name="warehouse_capacity_reasonableness",
                    constraint_type="business_logic",
                    description="Warehouse capacity must be positive",
                    condition="capacity > 0",
                    error_message="Warehouse capacity must be positive",
                    affected_entities=["Warehouse"],
                ),
                BusinessConstraint(
                    name="inventory_quantity_reasonableness",
                    constraint_type="business_logic",
                    description="Inventory quantity must be non-negative",
                    condition="quantity >= 0",
                    error_message="Inventory quantity cannot be negative",
                    affected_entities=["Inventory"],
                ),
                BusinessConstraint(
                    name="shipment_temporal_consistency",
                    constraint_type="temporal_consistency",
                    description="Shipment delivery date cannot be earlier than ship date",
                    condition="delivery_date >= ship_date",
                    error_message="Shipment delivery date cannot be earlier than ship date",
                    affected_entities=["Shipment"],
                ),
            ],
        )
        schemas.append(supply_chain_schema)
        recommendation_schema = DatabaseSchema(
            name="recommendation_system",
            domain="E-commerce",
            description="Recommendation System Graph Database Schema",
            node_types=[
                NodeType(
                    "User",
                    [
                        Property("user_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("age", "int"),
                        Property("gender", "string"),
                        Property("preferences", "string"),
                        Property("purchase_history", "string"),
                    ],
                ),
                NodeType(
                    "Item",
                    [
                        Property("item_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("category", "string"),
                        Property("price", "float"),
                        Property("popularity", "float"),
                        Property("features", "string"),
                    ],
                ),
                NodeType(
                    "Interaction",
                    [
                        Property("interaction_id", "string", unique=True, indexed=True),
                        Property("interaction_type", "string"),
                        Property("timestamp", "datetime"),
                        Property("rating", "float"),
                        Property("duration", "int"),
                    ],
                ),
                NodeType(
                    "Recommendation",
                    [
                        Property(
                            "recommendation_id", "string", unique=True, indexed=True
                        ),
                        Property("algorithm", "string"),
                        Property("confidence", "float"),
                        Property("timestamp", "datetime"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType("INTERACTS_WITH", "User", "Item", cardinality="N:M"),
                RelationshipType(
                    "GENERATES",
                    "Interaction",
                    "Recommendation",
                    cardinality="1:1",
                    max_connections_per_from=1,
                    max_connections_per_to=1,
                ),
                RelationshipType(
                    "RECOMMENDS",
                    "Recommendation",
                    "Item",
                    cardinality="1:1",
                    max_connections_per_from=1,
                    max_connections_per_to=1,
                ),
                RelationshipType(
                    "TARGETS",
                    "Recommendation",
                    "User",
                    cardinality="1:1",
                    max_connections_per_from=1,
                    max_connections_per_to=1,
                ),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="user_age_reasonableness",
                    constraint_type="business_logic",
                    description="User age must be within reasonable range",
                    condition="age >= 13 AND age <= 100",
                    error_message="User age must be between 13-100 years",
                    affected_entities=["User"],
                ),
                BusinessConstraint(
                    name="item_price_reasonableness",
                    constraint_type="business_logic",
                    description="Item price must be positive",
                    condition="price > 0",
                    error_message="Item price must be positive",
                    affected_entities=["Item"],
                ),
                BusinessConstraint(
                    name="item_popularity_reasonableness",
                    constraint_type="business_logic",
                    description="Item popularity must be between 0-1",
                    condition="popularity >= 0.0 AND popularity <= 1.0",
                    error_message="Item popularity must be between 0-1",
                    affected_entities=["Item"],
                ),
                BusinessConstraint(
                    name="interaction_rating_reasonableness",
                    constraint_type="business_logic",
                    description="Interaction rating must be between 1-5",
                    condition="rating >= 1.0 AND rating <= 5.0",
                    error_message="Interaction rating must be between 1-5",
                    affected_entities=["Interaction"],
                ),
                BusinessConstraint(
                    name="recommendation_confidence_reasonableness",
                    constraint_type="business_logic",
                    description="Recommendation confidence must be between 0-1",
                    condition="confidence >= 0.0 AND confidence <= 1.0",
                    error_message="Recommendation confidence must be between 0-1",
                    affected_entities=["Recommendation"],
                ),
                BusinessConstraint(
                    name="interaction_duration_reasonableness",
                    constraint_type="business_logic",
                    description="Interaction duration must be positive",
                    condition="duration > 0",
                    error_message="Interaction duration must be positive",
                    affected_entities=["Interaction"],
                ),
            ],
        )
        schemas.append(recommendation_schema)
        return schemas

    def _generate_transportation_schemas(self) -> List[DatabaseSchema]:
        schemas = []
        transport_schema = DatabaseSchema(
            name="transportation_system",
            domain="Transportation",
            description="Transportation System Graph Database Schema",
            node_types=[
                NodeType(
                    "Station",
                    [
                        Property("station_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("type", "string"),
                        Property("location", "string"),
                        Property("capacity", "int"),
                        Property("operating_hours", "string"),
                    ],
                ),
                NodeType(
                    "Route",
                    [
                        Property("route_id", "string", unique=True, indexed=True),
                        Property("route_name", "string"),
                        Property("transport_type", "string"),
                        Property("distance", "float"),
                        Property("duration", "int"),
                        Property("frequency", "int"),
                    ],
                ),
                NodeType(
                    "Vehicle",
                    [
                        Property("vehicle_id", "string", unique=True, indexed=True),
                        Property("type", "string"),
                        Property("capacity", "int"),
                        Property("status", "string"),
                        Property("last_maintenance", "date"),
                    ],
                ),
                NodeType(
                    "Passenger",
                    [
                        Property("passenger_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("age", "int"),
                        Property("ticket_type", "string"),
                        Property("travel_frequency", "string"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType("CONNECTS", "Route", "Station", cardinality="N:M"),
                RelationshipType(
                    "OPERATES_ON",
                    "Vehicle",
                    "Route",
                    cardinality="N:1",
                    max_connections_per_to=1,
                ),
                RelationshipType(
                    "BOARDS_AT", "Passenger", "Station", cardinality="N:M"
                ),
                RelationshipType("TRAVELS_ON", "Passenger", "Route", cardinality="N:M"),
                RelationshipType("TRANSFERS_AT", "Route", "Station", cardinality="N:M"),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="station_capacity_reasonableness",
                    constraint_type="business_logic",
                    description="Station capacity must be positive",
                    condition="capacity > 0",
                    error_message="Station capacity must be positive",
                    affected_entities=["Station"],
                ),
                BusinessConstraint(
                    name="route_distance_reasonableness",
                    constraint_type="business_logic",
                    description="Route distance must be positive",
                    condition="distance > 0",
                    error_message="Route distance must be positive",
                    affected_entities=["Route"],
                ),
                BusinessConstraint(
                    name="route_duration_reasonableness",
                    constraint_type="business_logic",
                    description="Route duration must be positive",
                    condition="duration > 0",
                    error_message="Route duration must be positive",
                    affected_entities=["Route"],
                ),
                BusinessConstraint(
                    name="vehicle_capacity_reasonableness",
                    constraint_type="business_logic",
                    description="Vehicle capacity must be positive",
                    condition="capacity > 0",
                    error_message="Vehicle capacity must be positive",
                    affected_entities=["Vehicle"],
                ),
                BusinessConstraint(
                    name="passenger_age_reasonableness",
                    constraint_type="business_logic",
                    description="Passenger age must be within reasonable range",
                    condition="age >= 0 AND age <= 120",
                    error_message="Passenger age must be between 0-120 years",
                    affected_entities=["Passenger"],
                ),
                BusinessConstraint(
                    name="vehicle_maintenance_temporal_consistency",
                    constraint_type="temporal_consistency",
                    description="Vehicle last maintenance date cannot be in the future",
                    condition="last_maintenance <= CURRENT_DATE",
                    error_message="Vehicle last maintenance date cannot be in the future",
                    affected_entities=["Vehicle"],
                ),
            ],
        )
        schemas.append(transport_schema)
        rideshare_schema = DatabaseSchema(
            name="rideshare_system",
            domain="Transportation",
            description="Rideshare System Graph Database Schema",
            node_types=[
                NodeType(
                    "Driver",
                    [
                        Property("driver_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("rating", "float"),
                        Property("vehicle_type", "string"),
                        Property("license_plate", "string"),
                        Property("availability", "boolean"),
                    ],
                ),
                NodeType(
                    "Rider",
                    [
                        Property("rider_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("rating", "float"),
                        Property("payment_method", "string"),
                        Property("preferred_vehicle", "string"),
                    ],
                ),
                NodeType(
                    "Trip",
                    [
                        Property("trip_id", "string", unique=True, indexed=True),
                        Property("pickup_location", "string"),
                        Property("dropoff_location", "string"),
                        Property("start_time", "datetime"),
                        Property("end_time", "datetime"),
                        Property("fare", "float"),
                        Property("distance", "float"),
                    ],
                ),
                NodeType(
                    "Vehicle",
                    [
                        Property("vehicle_id", "string", unique=True, indexed=True),
                        Property("make", "string"),
                        Property("model", "string"),
                        Property("year", "int"),
                        Property("capacity", "int"),
                        Property("fuel_type", "string"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType(
                    "DRIVES",
                    "Driver",
                    "Vehicle",
                    cardinality="1:1",
                    max_connections_per_from=1,
                    max_connections_per_to=1,
                ),
                RelationshipType("TAKES", "Rider", "Trip", cardinality="N:M"),
                RelationshipType("PROVIDES", "Driver", "Trip", cardinality="1:N"),
                RelationshipType(
                    "USES",
                    "Trip",
                    "Vehicle",
                    cardinality="1:1",
                    max_connections_per_from=1,
                    max_connections_per_to=1,
                ),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="driver_rating_reasonableness",
                    constraint_type="business_logic",
                    description="Driver rating must be between 1-5",
                    condition="rating >= 1.0 AND rating <= 5.0",
                    error_message="Driver rating must be between 1-5",
                    affected_entities=["Driver"],
                ),
                BusinessConstraint(
                    name="rider_rating_reasonableness",
                    constraint_type="business_logic",
                    description="Rider rating must be between 1-5",
                    condition="rating >= 1.0 AND rating <= 5.0",
                    error_message="Rider rating must be between 1-5",
                    affected_entities=["Rider"],
                ),
                BusinessConstraint(
                    name="trip_fare_reasonableness",
                    constraint_type="business_logic",
                    description="Trip fare must be positive",
                    condition="fare > 0",
                    error_message="Trip fare must be positive",
                    affected_entities=["Trip"],
                ),
                BusinessConstraint(
                    name="trip_distance_reasonableness",
                    constraint_type="business_logic",
                    description="Trip distance must be positive",
                    condition="distance > 0",
                    error_message="Trip distance must be positive",
                    affected_entities=["Trip"],
                ),
                BusinessConstraint(
                    name="vehicle_year_reasonableness",
                    constraint_type="business_logic",
                    description="Vehicle year must be within reasonable range",
                    condition="year >= 1990 AND year <= 2024",
                    error_message="Vehicle year must be between 1990-2024",
                    affected_entities=["Vehicle"],
                ),
                BusinessConstraint(
                    name="trip_temporal_consistency",
                    constraint_type="temporal_consistency",
                    description="Trip end time cannot be earlier than start time",
                    condition="end_time >= start_time",
                    error_message="Trip end time cannot be earlier than start time",
                    affected_entities=["Trip"],
                ),
            ],
        )
        schemas.append(rideshare_schema)
        logistics_schema = DatabaseSchema(
            name="logistics_system",
            domain="Transportation",
            description="Logistics System Graph Database Schema",
            node_types=[
                NodeType(
                    "Package",
                    [
                        Property("package_id", "string", unique=True, indexed=True),
                        Property("weight", "float"),
                        Property("dimensions", "string"),
                        Property("fragile", "boolean"),
                        Property("value", "float"),
                        Property("priority", "string"),
                    ],
                ),
                NodeType(
                    "DeliveryRoute",
                    [
                        Property("route_id", "string", unique=True, indexed=True),
                        Property("start_location", "string"),
                        Property("end_location", "string"),
                        Property("estimated_time", "int"),
                        Property("distance", "float"),
                        Property("traffic_condition", "string"),
                    ],
                ),
                NodeType(
                    "DeliveryPerson",
                    [
                        Property("person_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("vehicle_type", "string"),
                        Property("experience_years", "int"),
                        Property("rating", "float"),
                    ],
                ),
                NodeType(
                    "Warehouse",
                    [
                        Property("warehouse_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("location", "string"),
                        Property("capacity", "int"),
                        Property("operating_hours", "string"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType(
                    "DELIVERS",
                    "DeliveryPerson",
                    "Package",
                    cardinality="1:N",
                    max_connections_per_from=20,
                ),
                RelationshipType(
                    "FOLLOWS",
                    "Package",
                    "DeliveryRoute",
                    cardinality="1:1",
                    max_connections_per_from=1,
                    max_connections_per_to=1,
                ),
                RelationshipType("STORES", "Warehouse", "Package", cardinality="1:N"),
                RelationshipType(
                    "ASSIGNED_TO",
                    "DeliveryPerson",
                    "DeliveryRoute",
                    cardinality="1:N",
                    max_connections_per_from=5,
                ),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="package_weight_reasonableness",
                    constraint_type="business_logic",
                    description="Package weight must be positive",
                    condition="weight > 0",
                    error_message="Package weight must be positive",
                    affected_entities=["Package"],
                ),
                BusinessConstraint(
                    name="package_value_reasonableness",
                    constraint_type="business_logic",
                    description="Package value must be positive",
                    condition="value > 0",
                    error_message="Package value must be positive",
                    affected_entities=["Package"],
                ),
                BusinessConstraint(
                    name="delivery_person_experience_reasonableness",
                    constraint_type="business_logic",
                    description="Delivery person experience must be non-negative",
                    condition="experience_years >= 0 AND experience_years <= 50",
                    error_message="Delivery person experience must be between 0-50 years",
                    affected_entities=["DeliveryPerson"],
                ),
                BusinessConstraint(
                    name="delivery_person_rating_reasonableness",
                    constraint_type="business_logic",
                    description="Delivery person rating must be between 1-5",
                    condition="rating >= 1.0 AND rating <= 5.0",
                    error_message="Delivery person rating must be between 1-5",
                    affected_entities=["DeliveryPerson"],
                ),
                BusinessConstraint(
                    name="delivery_route_distance_reasonableness",
                    constraint_type="business_logic",
                    description="Delivery route distance must be positive",
                    condition="distance > 0",
                    error_message="Delivery route distance must be positive",
                    affected_entities=["DeliveryRoute"],
                ),
                BusinessConstraint(
                    name="warehouse_capacity_reasonableness",
                    constraint_type="business_logic",
                    description="Warehouse capacity must be positive",
                    condition="capacity > 0",
                    error_message="Warehouse capacity must be positive",
                    affected_entities=["Warehouse"],
                ),
            ],
        )
        schemas.append(logistics_schema)
        return schemas

    def _generate_real_estate_schemas(self) -> List[DatabaseSchema]:
        schemas = []
        real_estate_schema = DatabaseSchema(
            name="real_estate_system",
            domain="Real Estate",
            description="Real Estate System Graph Database Schema",
            node_types=[
                NodeType(
                    "Property",
                    [
                        Property("property_id", "string", unique=True, indexed=True),
                        Property("address", "string"),
                        Property("property_type", "string"),
                        Property("size", "float"),
                        Property("price", "float"),
                        Property("bedrooms", "int"),
                        Property("bathrooms", "int"),
                        Property("year_built", "int"),
                    ],
                ),
                NodeType(
                    "Owner",
                    [
                        Property("owner_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("contact_info", "string"),
                        Property("ownership_type", "string"),
                        Property("purchase_date", "date"),
                    ],
                ),
                NodeType(
                    "Agent",
                    [
                        Property("agent_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("company", "string"),
                        Property("license_number", "string"),
                        Property("experience_years", "int"),
                    ],
                ),
                NodeType(
                    "Neighborhood",
                    [
                        Property(
                            "neighborhood_id", "string", unique=True, indexed=True
                        ),
                        Property("name", "string"),
                        Property("city", "string"),
                        Property("average_price", "float"),
                        Property("crime_rate", "float"),
                        Property("school_rating", "float"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType("OWNS", "Owner", "Property", cardinality="1:N"),
                RelationshipType("SELLS", "Agent", "Property", cardinality="1:N"),
                RelationshipType(
                    "LOCATED_IN",
                    "Property",
                    "Neighborhood",
                    cardinality="N:1",
                    max_connections_per_to=1,
                ),
                RelationshipType(
                    "REPRESENTS",
                    "Agent",
                    "Owner",
                    cardinality="1:N",
                    max_connections_per_from=10,
                ),
                RelationshipType("NEARBY", "Property", "Property", cardinality="N:M"),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="property_price_reasonableness",
                    constraint_type="business_logic",
                    description="Property price must be positive",
                    condition="price > 0",
                    error_message="Property price must be positive",
                    affected_entities=["Property"],
                ),
                BusinessConstraint(
                    name="property_size_reasonableness",
                    constraint_type="business_logic",
                    description="Property size must be positive",
                    condition="size > 0",
                    error_message="Property size must be positive",
                    affected_entities=["Property"],
                ),
                BusinessConstraint(
                    name="property_room_count_reasonableness",
                    constraint_type="business_logic",
                    description="Property room count must be positive",
                    condition="bedrooms >= 0 AND bathrooms >= 0",
                    error_message="Property room count cannot be negative",
                    affected_entities=["Property"],
                ),
                BusinessConstraint(
                    name="property_year_built_reasonableness",
                    constraint_type="business_logic",
                    description="Property year built must be within reasonable range",
                    condition="year_built >= 1800 AND year_built <= 2024",
                    error_message="Property year built must be between 1800-2024",
                    affected_entities=["Property"],
                ),
                BusinessConstraint(
                    name="agent_experience_reasonableness",
                    constraint_type="business_logic",
                    description="Agent experience must be non-negative",
                    condition="experience_years >= 0 AND experience_years <= 50",
                    error_message="Agent experience must be between 0-50 years",
                    affected_entities=["Agent"],
                ),
                BusinessConstraint(
                    name="neighborhood_crime_rate_reasonableness",
                    constraint_type="business_logic",
                    description="Neighborhood crime rate must be between 0-1",
                    condition="crime_rate >= 0.0 AND crime_rate <= 1.0",
                    error_message="Neighborhood crime rate must be between 0-1",
                    affected_entities=["Neighborhood"],
                ),
            ],
        )
        schemas.append(real_estate_schema)
        property_management_schema = DatabaseSchema(
            name="property_management",
            domain="Real Estate",
            description="Property Management System Graph Database Schema",
            node_types=[
                NodeType(
                    "Building",
                    [
                        Property("building_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("address", "string"),
                        Property("floors", "int"),
                        Property("units", "int"),
                        Property("year_built", "int"),
                        Property("amenities", "string"),
                    ],
                ),
                NodeType(
                    "Tenant",
                    [
                        Property("tenant_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("contact_info", "string"),
                        Property("lease_start", "date"),
                        Property("lease_end", "date"),
                        Property("rent_amount", "float"),
                    ],
                ),
                NodeType(
                    "Maintenance",
                    [
                        Property("maintenance_id", "string", unique=True, indexed=True),
                        Property("issue_type", "string"),
                        Property("description", "string"),
                        Property("priority", "string"),
                        Property("status", "string"),
                        Property("report_date", "date"),
                    ],
                ),
                NodeType(
                    "Manager",
                    [
                        Property("manager_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("company", "string"),
                        Property("experience_years", "int"),
                        Property("certification", "string"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType(
                    "LIVES_IN",
                    "Tenant",
                    "Building",
                    cardinality="N:1",
                    max_connections_per_to=1,
                ),
                RelationshipType(
                    "MANAGES",
                    "Manager",
                    "Building",
                    cardinality="1:N",
                    max_connections_per_from=5,
                ),
                RelationshipType("REPORTS", "Tenant", "Maintenance", cardinality="1:N"),
                RelationshipType(
                    "ADDRESSES", "Manager", "Maintenance", cardinality="1:N"
                ),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="building_floors_reasonableness",
                    constraint_type="business_logic",
                    description="Building floors must be positive",
                    condition="floors > 0",
                    error_message="Building floors must be positive",
                    affected_entities=["Building"],
                ),
                BusinessConstraint(
                    name="building_units_reasonableness",
                    constraint_type="business_logic",
                    description="Building units must be positive",
                    condition="units > 0",
                    error_message="Building units must be positive",
                    affected_entities=["Building"],
                ),
                BusinessConstraint(
                    name="building_year_built_reasonableness",
                    constraint_type="business_logic",
                    description="Building year built must be within reasonable range",
                    condition="year_built >= 1800 AND year_built <= 2024",
                    error_message="Building year built must be between 1800-2024",
                    affected_entities=["Building"],
                ),
                BusinessConstraint(
                    name="rent_amount_reasonableness",
                    constraint_type="business_logic",
                    description="Rent amount must be positive",
                    condition="rent_amount > 0",
                    error_message="Rent amount must be positive",
                    affected_entities=["Tenant"],
                ),
                BusinessConstraint(
                    name="lease_temporal_consistency",
                    constraint_type="temporal_consistency",
                    description="Lease end date cannot be earlier than start date",
                    condition="lease_end >= lease_start",
                    error_message="Lease end date cannot be earlier than start date",
                    affected_entities=["Tenant"],
                ),
                BusinessConstraint(
                    name="maintenance_priority_consistency",
                    constraint_type="business_logic",
                    description="Maintenance priority must be valid",
                    condition="priority IN ('low', 'medium', 'high', 'urgent')",
                    error_message="Maintenance priority must be a valid level",
                    affected_entities=["Maintenance"],
                ),
            ],
        )
        schemas.append(property_management_schema)
        real_estate_investment_schema = DatabaseSchema(
            name="real_estate_investment",
            domain="Real Estate",
            description="Real Estate Investment System Graph Database Schema",
            node_types=[
                NodeType(
                    "Investment",
                    [
                        Property("investment_id", "string", unique=True, indexed=True),
                        Property("investment_type", "string"),
                        Property("amount", "float"),
                        Property("expected_return", "float"),
                        Property("risk_level", "string"),
                        Property("investment_date", "date"),
                    ],
                ),
                NodeType(
                    "Investor",
                    [
                        Property("investor_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("investment_style", "string"),
                        Property("risk_tolerance", "string"),
                        Property("total_assets", "float"),
                    ],
                ),
                NodeType(
                    "Market",
                    [
                        Property("market_id", "string", unique=True, indexed=True),
                        Property("location", "string"),
                        Property("market_type", "string"),
                        Property("growth_rate", "float"),
                        Property("volatility", "float"),
                    ],
                ),
                NodeType(
                    "Portfolio",
                    [
                        Property("portfolio_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("total_value", "float"),
                        Property("diversification", "float"),
                        Property("performance", "float"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType("MAKES", "Investor", "Investment", cardinality="1:N"),
                RelationshipType(
                    "INVESTS_IN",
                    "Investment",
                    "Market",
                    cardinality="1:1",
                    max_connections_per_from=1,
                    max_connections_per_to=1,
                ),
                RelationshipType(
                    "CONTAINS", "Portfolio", "Investment", cardinality="1:N"
                ),
                RelationshipType(
                    "MANAGES",
                    "Investor",
                    "Portfolio",
                    cardinality="1:N",
                    max_connections_per_from=3,
                ),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="investment_amount_reasonableness",
                    constraint_type="business_logic",
                    description="Investment amount must be positive",
                    condition="amount > 0",
                    error_message="Investment amount must be positive",
                    affected_entities=["Investment"],
                ),
                BusinessConstraint(
                    name="investment_expected_return_reasonableness",
                    constraint_type="business_logic",
                    description="Investment expected return must be within reasonable range",
                    condition="expected_return >= -1.0 AND expected_return <= 10.0",
                    error_message="Investment expected return must be between -100% to 1000%",
                    affected_entities=["Investment"],
                ),
                BusinessConstraint(
                    name="investor_total_assets_reasonableness",
                    constraint_type="business_logic",
                    description="Investor total assets must be positive",
                    condition="total_assets > 0",
                    error_message="Investor total assets must be positive",
                    affected_entities=["Investor"],
                ),
                BusinessConstraint(
                    name="market_growth_rate_reasonableness",
                    constraint_type="business_logic",
                    description="Market growth rate must be within reasonable range",
                    condition="growth_rate >= -1.0 AND growth_rate <= 5.0",
                    error_message="Market growth rate must be between -100% to 500%",
                    affected_entities=["Market"],
                ),
                BusinessConstraint(
                    name="portfolio_total_value_reasonableness",
                    constraint_type="business_logic",
                    description="Portfolio total value must be positive",
                    condition="total_value > 0",
                    error_message="Portfolio total value must be positive",
                    affected_entities=["Portfolio"],
                ),
                BusinessConstraint(
                    name="portfolio_diversification_reasonableness",
                    constraint_type="business_logic",
                    description="Portfolio diversification must be between 0-1",
                    condition="diversification >= 0.0 AND diversification <= 1.0",
                    error_message="Portfolio diversification must be between 0-1",
                    affected_entities=["Portfolio"],
                ),
            ],
        )
        schemas.append(real_estate_investment_schema)
        return schemas

    def _generate_entertainment_schemas(self) -> List[DatabaseSchema]:
        schemas = []
        entertainment_schema = DatabaseSchema(
            name="entertainment_system",
            domain="Entertainment",
            description="Entertainment System Graph Database Schema",
            node_types=[
                NodeType(
                    "Movie",
                    [
                        Property("movie_id", "string", unique=True, indexed=True),
                        Property("title", "string"),
                        Property("genre", "string"),
                        Property("release_year", "int"),
                        Property("rating", "float"),
                        Property("duration", "int"),
                        Property("budget", "float"),
                        Property("box_office", "float"),
                    ],
                ),
                NodeType(
                    "Actor",
                    [
                        Property("actor_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("age", "int"),
                        Property("nationality", "string"),
                        Property("awards", "int"),
                        Property("net_worth", "float"),
                    ],
                ),
                NodeType(
                    "Director",
                    [
                        Property("director_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("age", "int"),
                        Property("style", "string"),
                        Property("awards", "int"),
                    ],
                ),
                NodeType(
                    "Studio",
                    [
                        Property("studio_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("founded_year", "int"),
                        Property("location", "string"),
                        Property("revenue", "float"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType("STARS_IN", "Actor", "Movie", cardinality="N:M"),
                RelationshipType("DIRECTS", "Director", "Movie", cardinality="1:N"),
                RelationshipType("PRODUCES", "Studio", "Movie", cardinality="1:N"),
                RelationshipType(
                    "COLLABORATES_WITH", "Actor", "Director", cardinality="N:M"
                ),
                RelationshipType("SIMILAR_TO", "Movie", "Movie", cardinality="N:M"),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="movie_rating_reasonableness",
                    constraint_type="business_logic",
                    description="Movie rating must be between 1-10",
                    condition="rating >= 1.0 AND rating <= 10.0",
                    error_message="Movie rating must be between 1-10",
                    affected_entities=["Movie"],
                ),
                BusinessConstraint(
                    name="movie_duration_reasonableness",
                    constraint_type="business_logic",
                    description="Movie duration must be positive",
                    condition="duration > 0 AND duration <= 300",
                    error_message="Movie duration must be between 1-300 minutes",
                    affected_entities=["Movie"],
                ),
                BusinessConstraint(
                    name="movie_budget_reasonableness",
                    constraint_type="business_logic",
                    description="Movie budget must be positive",
                    condition="budget > 0",
                    error_message="Movie budget must be positive",
                    affected_entities=["Movie"],
                ),
                BusinessConstraint(
                    name="movie_box_office_reasonableness",
                    constraint_type="business_logic",
                    description="Movie box office must be non-negative",
                    condition="box_office >= 0",
                    error_message="Movie box office cannot be negative",
                    affected_entities=["Movie"],
                ),
                BusinessConstraint(
                    name="actor_age_reasonableness",
                    constraint_type="business_logic",
                    description="Actor age must be within reasonable range",
                    condition="age >= 0 AND age <= 100",
                    error_message="Actor age must be between 0-100 years",
                    affected_entities=["Actor"],
                ),
                BusinessConstraint(
                    name="movie_release_year_reasonableness",
                    constraint_type="business_logic",
                    description="Movie release year must be within reasonable range",
                    condition="release_year >= 1900 AND release_year <= 2024",
                    error_message="Movie release year must be between 1900-2024",
                    affected_entities=["Movie"],
                ),
            ],
            cycle_patterns=[
                CyclePattern(
                    id="entertainment_cycle_1",
                    name="movie_similarity_cycle",
                    description="Movie-Similarity-Movie cycle pattern",
                    cycle_path=[
                        "Movie",
                        "SIMILAR_TO",
                        "Movie",
                        "SIMILAR_TO",
                        "Movie",
                        "SIMILAR_TO",
                        "Movie",
                    ],
                    cycle_length=7,
                    is_valid=True,
                    explanation="Movies can be similar to each other, forming a cycle of similarity relationships",
                    business_logic="Follows entertainment logic, movies can have similar relationships forming cycles",
                    node_types_involved=["Movie"],
                    relationship_types_involved=["SIMILAR_TO"],
                    instance_cycle_description="Multiple movies are similar to each other, eventually forming a cycle",
                    example_cycle={
                        "description": "Three movies form a similarity cycle",
                        "cycle_instances": [
                            {"type": "Movie", "id": "Movie_001", "title": "Movie A"},
                            {
                                "type": "SIMILAR_TO",
                                "id": "SIMILAR_TO_001",
                                "from": "Movie_001",
                                "to": "Movie_002",
                            },
                            {"type": "Movie", "id": "Movie_002", "title": "Movie B"},
                            {
                                "type": "SIMILAR_TO",
                                "id": "SIMILAR_TO_002",
                                "from": "Movie_002",
                                "to": "Movie_003",
                            },
                            {"type": "Movie", "id": "Movie_003", "title": "Movie C"},
                            {
                                "type": "SIMILAR_TO",
                                "id": "SIMILAR_TO_003",
                                "from": "Movie_003",
                                "to": "Movie_001",
                            },
                        ],
                    },
                    constraints={
                        "min_cycle_length": 3,
                        "max_cycle_length": 10,
                        "business_rules": [
                            "Movie similarity relationships can form cycles",
                            "Similar movies should have comparable genres or themes",
                        ],
                    },
                )
            ],
        )
        schemas.append(entertainment_schema)
        music_schema = DatabaseSchema(
            name="music_system",
            domain="Entertainment",
            description="Music System Graph Database Schema",
            node_types=[
                NodeType(
                    "Artist",
                    [
                        Property("artist_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("genre", "string"),
                        Property("country", "string"),
                        Property("debut_year", "int"),
                        Property("albums_count", "int"),
                    ],
                ),
                NodeType(
                    "Album",
                    [
                        Property("album_id", "string", unique=True, indexed=True),
                        Property("title", "string"),
                        Property("release_date", "date"),
                        Property("genre", "string"),
                        Property("tracks_count", "int"),
                        Property("sales", "int"),
                    ],
                ),
                NodeType(
                    "Song",
                    [
                        Property("song_id", "string", unique=True, indexed=True),
                        Property("title", "string"),
                        Property("duration", "int"),
                        Property("genre", "string"),
                        Property("popularity", "float"),
                        Property("release_year", "int"),
                    ],
                ),
                NodeType(
                    "Label",
                    [
                        Property("label_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("founded_year", "int"),
                        Property("location", "string"),
                        Property("artists_count", "int"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType("SINGS", "Artist", "Song", cardinality="N:M"),
                RelationshipType("CONTAINS", "Album", "Song", cardinality="1:N"),
                RelationshipType("RELEASES", "Artist", "Album", cardinality="1:N"),
                RelationshipType(
                    "SIGNS_WITH",
                    "Artist",
                    "Label",
                    cardinality="N:1",
                    max_connections_per_to=1,
                ),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="song_duration_reasonableness",
                    constraint_type="business_logic",
                    description="Song duration must be positive",
                    condition="duration > 0 AND duration <= 600",
                    error_message="Song duration must be between 1-600 seconds",
                    affected_entities=["Song"],
                ),
                BusinessConstraint(
                    name="song_popularity_reasonableness",
                    constraint_type="business_logic",
                    description="Song popularity must be between 0-1",
                    condition="popularity >= 0.0 AND popularity <= 1.0",
                    error_message="Song popularity must be between 0-1",
                    affected_entities=["Song"],
                ),
                BusinessConstraint(
                    name="album_tracks_count_reasonableness",
                    constraint_type="business_logic",
                    description="Album tracks count must be positive",
                    condition="tracks_count > 0",
                    error_message="Album tracks count must be positive",
                    affected_entities=["Album"],
                ),
                BusinessConstraint(
                    name="album_sales_reasonableness",
                    constraint_type="business_logic",
                    description="Album sales must be non-negative",
                    condition="sales >= 0",
                    error_message="Album sales cannot be negative",
                    affected_entities=["Album"],
                ),
                BusinessConstraint(
                    name="artist_debut_year_reasonableness",
                    constraint_type="business_logic",
                    description="Artist debut year must be within reasonable range",
                    condition="debut_year >= 1900 AND debut_year <= 2024",
                    error_message="Artist debut year must be between 1900-2024",
                    affected_entities=["Artist"],
                ),
                BusinessConstraint(
                    name="label_artists_count_reasonableness",
                    constraint_type="business_logic",
                    description="Label artists count must be non-negative",
                    condition="artists_count >= 0",
                    error_message="Label artists count cannot be negative",
                    affected_entities=["Label"],
                ),
            ],
        )
        schemas.append(music_schema)
        gaming_schema = DatabaseSchema(
            name="gaming_system",
            domain="Entertainment",
            description="Gaming System Graph Database Schema",
            node_types=[
                NodeType(
                    "Game",
                    [
                        Property("game_id", "string", unique=True, indexed=True),
                        Property("title", "string"),
                        Property("genre", "string"),
                        Property("platform", "string"),
                        Property("release_date", "date"),
                        Property("rating", "float"),
                        Property("price", "float"),
                    ],
                ),
                NodeType(
                    "Player",
                    [
                        Property("player_id", "string", unique=True, indexed=True),
                        Property("username", "string"),
                        Property("level", "int"),
                        Property("experience_points", "int"),
                        Property("play_time", "int"),
                        Property("achievements", "int"),
                    ],
                ),
                NodeType(
                    "Developer",
                    [
                        Property("developer_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("country", "string"),
                        Property("founded_year", "int"),
                        Property("games_count", "int"),
                    ],
                ),
                NodeType(
                    "Achievement",
                    [
                        Property("achievement_id", "string", unique=True, indexed=True),
                        Property("name", "string"),
                        Property("description", "string"),
                        Property("difficulty", "string"),
                        Property("rarity", "string"),
                    ],
                ),
            ],
            relationship_types=[
                RelationshipType("PLAYS", "Player", "Game", cardinality="N:M"),
                RelationshipType("DEVELOPS", "Developer", "Game", cardinality="1:N"),
                RelationshipType("UNLOCKS", "Player", "Achievement", cardinality="N:M"),
                RelationshipType(
                    "REQUIRES",
                    "Achievement",
                    "Game",
                    cardinality="1:1",
                    max_connections_per_from=1,
                    max_connections_per_to=1,
                ),
            ],
            business_constraints=[
                BusinessConstraint(
                    name="game_rating_reasonableness",
                    constraint_type="business_logic",
                    description="Game rating must be between 1-10",
                    condition="rating >= 1.0 AND rating <= 10.0",
                    error_message="Game rating must be between 1-10",
                    affected_entities=["Game"],
                ),
                BusinessConstraint(
                    name="game_price_reasonableness",
                    constraint_type="business_logic",
                    description="Game price must be non-negative",
                    condition="price >= 0",
                    error_message="Game price cannot be negative",
                    affected_entities=["Game"],
                ),
                BusinessConstraint(
                    name="player_level_reasonableness",
                    constraint_type="business_logic",
                    description="Player level must be positive",
                    condition="level > 0",
                    error_message="Player level must be positive",
                    affected_entities=["Player"],
                ),
                BusinessConstraint(
                    name="player_experience_points_reasonableness",
                    constraint_type="business_logic",
                    description="Player experience points must be non-negative",
                    condition="experience_points >= 0",
                    error_message="Player experience points cannot be negative",
                    affected_entities=["Player"],
                ),
                BusinessConstraint(
                    name="player_play_time_reasonableness",
                    constraint_type="business_logic",
                    description="Player play time must be non-negative",
                    condition="play_time >= 0",
                    error_message="Player play time cannot be negative",
                    affected_entities=["Player"],
                ),
                BusinessConstraint(
                    name="player_achievements_reasonableness",
                    constraint_type="business_logic",
                    description="Player achievements must be non-negative",
                    condition="achievements >= 0",
                    error_message="Player achievements cannot be negative",
                    affected_entities=["Player"],
                ),
                BusinessConstraint(
                    name="developer_games_count_reasonableness",
                    constraint_type="business_logic",
                    description="Developer games count must be non-negative",
                    condition="games_count >= 0",
                    error_message="Developer games count cannot be negative",
                    affected_entities=["Developer"],
                ),
                BusinessConstraint(
                    name="game_release_date_reasonableness",
                    constraint_type="business_logic",
                    description="Game release date cannot be in the future",
                    condition="release_date <= CURRENT_DATE",
                    error_message="Game release date cannot be in the future",
                    affected_entities=["Game"],
                ),
            ],
        )
        schemas.append(gaming_schema)
        return schemas

    def save_schemas_to_json(
        self, schemas: Dict[str, List[DatabaseSchema]], output_dir: str
    ):
        os.makedirs(output_dir, exist_ok=True)
        for (domain, domain_schemas) in schemas.items():
            domain_data = []
            for schema in domain_schemas:
                schema_dict = asdict(schema)
                domain_data.append(schema_dict)
            output_file = os.path.join(output_dir, f"{domain}_schemas.json")
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(domain_data, f, ensure_ascii=False, indent=2)
            print(f"已保存 {domain} 领域模式到 {output_file}")

    def generate_cypher_ddl(self, schema: DatabaseSchema) -> str:
        cypher_statements = []
        for node_type in schema.node_types:
            for prop in node_type.properties:
                if prop.unique:
                    cypher_statements.append(
                        f"CREATE CONSTRAINT {node_type.name.lower()}_{prop.name}_unique FOR (n:{node_type.name}) REQUIRE n.{prop.name} IS UNIQUE;"
                    )
                if prop.indexed:
                    cypher_statements.append(
                        f"CREATE INDEX {node_type.name.lower()}_{prop.name}_index FOR (n:{node_type.name}) ON (n.{prop.name});"
                    )
        return "\n".join(cypher_statements)

    def generate_business_constraints_documentation(
        self, schema: DatabaseSchema
    ) -> str:
        if not schema.business_constraints:
            return f"# {schema.name} - 业务约束文档\n\n暂无业务约束定义。"
        doc_lines = [f"# {schema.name} - 业务约束文档", ""]
        constraint_types = {}
        for constraint in schema.business_constraints:
            if constraint.constraint_type not in constraint_types:
                constraint_types[constraint.constraint_type] = []
            constraint_types[constraint.constraint_type].append(constraint)
        type_descriptions = {
            "referential_integrity": "引用完整性约束 - 确保外键关系的有效性",
            "business_logic": "业务逻辑约束 - 确保业务规则的正确性",
            "state_consistency": "状态一致性约束 - 确保状态转换的合理性",
            "numerical_consistency": "数值一致性约束 - 确保数值计算的准确性",
            "temporal_consistency": "时间一致性约束 - 确保时间逻辑的正确性",
        }
        for (constraint_type, constraints) in constraint_types.items():
            doc_lines.append(
                f"## {type_descriptions.get(constraint_type, constraint_type)}"
            )
            doc_lines.append("")
            for constraint in constraints:
                doc_lines.append(f"### {constraint.name}")
                doc_lines.append(f"- **描述**: {constraint.description}")
                doc_lines.append(f"- **约束条件**: `{constraint.condition}`")
                if constraint.error_message:
                    doc_lines.append(f"- **错误信息**: {constraint.error_message}")
                if constraint.affected_entities:
                    doc_lines.append(
                        f"- **影响实体**: {', '.join(constraint.affected_entities)}"
                    )
                doc_lines.append("")
        return "\n".join(doc_lines)


def main():

    generator = SchemaGenerator()
    print("开始生成数据库模式...")
    all_schemas = generator.generate_all_schemas()
    output_dir = "./schemas"
    generator.save_schemas_to_json(all_schemas, output_dir)
    print(f"\n总共生成了 {sum((len(schemas) for schemas in all_schemas.values()))} 个数据库模式")


if __name__ == "__main__":

    main()
