from typing import Any, Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict, model_validator, field_validator


class ClientCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    instagram_username: Optional[str] = Field(default=None, max_length=80)
    business_information: str = ""
    location: str = ""
    delivery_information: str = ""
    business_hours: str = ""
    language: str = "English"
    tone: str = "Friendly"


class RegisterRequest(BaseModel):
    # `brand_name` is the canonical API field. `name` is accepted as a
    # backwards-compatible alias so older dashboard builds cannot break signup.
    brand_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    instagram_username: Optional[str] = Field(default=None, max_length=80)
    business_information: str = ""
    location: str = ""
    delivery_information: str = ""
    business_hours: str = ""
    language: str = "English"
    tone: str = "Friendly"
    automation_enabled: bool = True
    llm_enabled: bool = False

    @model_validator(mode="after")
    def validate_name(self):
        if not self.brand_name and not self.name:
            raise ValueError("brand_name or name is required")
        return self

    @property
    def resolved_name(self) -> str:
        return (self.brand_name or self.name or "").strip()


class AdminClientCreate(BaseModel):
    brand_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    instagram_username: Optional[str] = Field(default=None, max_length=80)
    business_information: str = ""
    location: str = ""
    delivery_information: str = ""
    business_hours: str = ""
    language: str = "English"
    tone: str = "Friendly"
    automation_enabled: bool = True
    llm_enabled: bool = False
    rate_limit_per_minute: int = Field(default=60, ge=1, le=10000)
    monthly_llm_limit: int = Field(default=1000, ge=0, le=10000000)
    monthly_llm_token_limit: int = Field(default=1000000, ge=0, le=1000000000)
    monthly_data_limit_mb: int = Field(default=1024, ge=0, le=1000000000)

class AdminClientUpdate(BaseModel):
    brand_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    instagram_username: Optional[str] = Field(default=None, max_length=80)
    business_information: Optional[str] = None
    location: Optional[str] = None
    delivery_information: Optional[str] = None
    business_hours: Optional[str] = None
    language: Optional[str] = None
    tone: Optional[str] = None
    automation_enabled: Optional[bool] = None
    llm_enabled: Optional[bool] = None
    rate_limit_per_minute: Optional[int] = Field(default=None, ge=1, le=10000)
    monthly_llm_limit: Optional[int] = Field(default=None, ge=0, le=10000000)
    monthly_llm_token_limit: Optional[int] = Field(default=None, ge=0, le=1000000000)
    monthly_data_limit_mb: Optional[int] = Field(default=None, ge=0, le=1000000000)


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sku: Optional[str] = Field(default=None, max_length=100)
    price: float = Field(ge=0)
    sale_price: Optional[float] = Field(default=None, ge=0)
    category: str = ""
    department: str = ""
    subcategory: str = ""
    product_type: str = ""
    target_gender: str = ""
    brand: str = ""
    description: str = ""
    sizes: list[str] = Field(default_factory=list)
    colors: list[str] = Field(default_factory=list)
    stock: bool = True
    quantity: int = Field(default=0, ge=0)
    product_url: str = ""
    image_url: str = ""
    active: bool = True
    instagram_post_id: Optional[str] = None
    instagram_media_id: Optional[str] = None

    @field_validator("sale_price")
    @classmethod
    def sale_not_above_price(cls, value, info):
        if value is not None and "price" in info.data and value > info.data["price"]:
            raise ValueError("sale_price cannot be greater than price")
        return value


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    sku: Optional[str] = None
    price: Optional[float] = Field(default=None, ge=0)
    sale_price: Optional[float] = Field(default=None, ge=0)
    category: Optional[str] = None
    department: Optional[str] = None
    subcategory: Optional[str] = None
    product_type: Optional[str] = None
    target_gender: Optional[str] = None
    brand: Optional[str] = None
    description: Optional[str] = None
    sizes: Optional[list[str]] = None
    colors: Optional[list[str]] = None
    stock: Optional[bool] = None
    quantity: Optional[int] = Field(default=None, ge=0)
    product_url: Optional[str] = None
    image_url: Optional[str] = None
    active: Optional[bool] = None
    instagram_post_id: Optional[str] = None
    instagram_media_id: Optional[str] = None


class BusinessSettingsUpdate(BaseModel):
    business_information: str = ""
    location: str = ""
    delivery_info: str = ""
    business_hours: str = ""
    contact: str = ""
    language: str = "English"
    tone: str = "Friendly"


class AutomationSettingsUpdate(BaseModel):
    automation_enabled: bool = True
    llm_enabled: bool = False
    language: str = "English"
    tone: str = "Friendly"
    human_handoff_on_unknown: bool = True
    low_confidence_threshold: float = Field(default=0.65, ge=0, le=1)


class InstagramAccountCreate(BaseModel):
    instagram_user_id: str = Field(min_length=1, max_length=200)
    username: str = Field(min_length=1, max_length=80)
    # Blank is allowed only for an already-connected account to keep its saved token.
    access_token: Optional[str] = Field(default=None, min_length=1)
    token_expires_at: Optional[str] = None


class ProductMappingCreate(BaseModel):
    instagram_post_id: str = ""
    instagram_media_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)


class TestInbound(BaseModel):
    sender_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=4000)
    product_id: Optional[str] = None
    source_type: str = "dm"
    source_id: Optional[str] = None


class ProductSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    entities: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=5, ge=1, le=20)
    exclude_product_id: Optional[str] = None


class ProductReindexRequest(BaseModel):
    pass


class HumanMessage(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
