"""
Holiday data models and validation.
"""

import uuid
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict


@dataclass
class RuleConfig:
    """Configuration for rule-based holidays (e.g., 2nd Monday of March)."""
    weekday: int  # 0=Monday, 6=Sunday
    ordinal: int  # 1=first, 2=second, etc. -1=last
    month: int    # 1-12

    def to_dict(self) -> Dict[str, int]:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'RuleConfig':
        return RuleConfig(
            weekday=data.get('weekday', 0),
            ordinal=data.get('ordinal', 1),
            month=data.get('month', 1)
        )


@dataclass
class Holiday:
    """
    Holiday data model.
    
    Types:
    - solar: Fixed solar date (month/day), recurring yearly
    - lunar: Lunar calendar date (lunarMonth/lunarDay), recurring yearly
    - specific: Specific date (year/month/day), one-time
    - rule: Rule-based (e.g., 2nd Monday of March)
    """
    id: str
    name: str
    type: str  # 'solar', 'lunar', 'specific', 'rule'
    recurring: bool = True
    
    # For solar/specific types
    month: Optional[int] = None
    day: Optional[int] = None
    year: Optional[int] = None
    
    # For lunar type
    lunarMonth: Optional[int] = None
    lunarDay: Optional[int] = None
    
    # For rule type
    rule: Optional[RuleConfig] = None
    
    # Vietnamese name (optional)
    nameVi: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'recurring': self.recurring,
        }
        
        if self.nameVi:
            result['nameVi'] = self.nameVi
            
        if self.type == 'solar' or self.type == 'specific':
            result['month'] = self.month
            result['day'] = self.day
            if self.year:
                result['year'] = self.year
                
        elif self.type == 'lunar':
            result['lunarMonth'] = self.lunarMonth
            result['lunarDay'] = self.lunarDay
            
        elif self.type == 'rule' and self.rule:
            result['rule'] = self.rule.to_dict()
            
        return result

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Holiday':
        """Create Holiday from dictionary."""
        rule = None
        if data.get('rule'):
            rule = RuleConfig.from_dict(data['rule'])
            
        return Holiday(
            id=data.get('id', str(uuid.uuid4())),
            name=data.get('name', ''),
            nameVi=data.get('nameVi'),
            type=data.get('type', 'solar'),
            recurring=data.get('recurring', True),
            month=data.get('month'),
            day=data.get('day'),
            year=data.get('year'),
            lunarMonth=data.get('lunarMonth'),
            lunarDay=data.get('lunarDay'),
            rule=rule
        )

    @staticmethod
    def generate_id() -> str:
        """Generate a unique ID for a new holiday."""
        return str(uuid.uuid4())[:8]


def validate_holiday(data: Dict[str, Any]) -> tuple[bool, str]:
    """
    Validate holiday data.
    Returns (is_valid, error_message).
    """
    if not data.get('name'):
        return False, 'Holiday name is required'
    
    holiday_type = data.get('type', 'solar')
    
    if holiday_type == 'solar':
        if not data.get('month') or not data.get('day'):
            return False, 'Solar holidays require month and day'
        if not (1 <= data['month'] <= 12):
            return False, 'Month must be between 1 and 12'
        if not (1 <= data['day'] <= 31):
            return False, 'Day must be between 1 and 31'
            
    elif holiday_type == 'lunar':
        if not data.get('lunarMonth') or not data.get('lunarDay'):
            return False, 'Lunar holidays require lunarMonth and lunarDay'
        if not (1 <= data['lunarMonth'] <= 12):
            return False, 'Lunar month must be between 1 and 12'
        if not (1 <= data['lunarDay'] <= 30):
            return False, 'Lunar day must be between 1 and 30'
            
    elif holiday_type == 'specific':
        if not data.get('year') or not data.get('month') or not data.get('day'):
            return False, 'Specific date holidays require year, month, and day'
            
    elif holiday_type == 'rule':
        rule = data.get('rule')
        if not rule:
            return False, 'Rule-based holidays require rule configuration'
        if not (0 <= rule.get('weekday', -1) <= 6):
            return False, 'Weekday must be between 0 (Monday) and 6 (Sunday)'
        if not (1 <= rule.get('month', 0) <= 12):
            return False, 'Month must be between 1 and 12'
    else:
        return False, f'Invalid holiday type: {holiday_type}'
    
    return True, ''
