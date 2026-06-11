export const FLAGS = {
  'Algeria': '🇩🇿', 'Argentina': '🇦🇷', 'Australia': '🇦🇺', 'Austria': '🇦🇹',
  'Belgium': '🇧🇪', 'Bosnia-Herzegovina': '🇧🇦', 'Bosnia and Herzegovina': '🇧🇦',
  'Brazil': '🇧🇷', 'Canada': '🇨🇦', 'Cape Verde': '🇨🇻', 'Cape Verde Islands': '🇨🇻',
  'Colombia': '🇨🇴', 'Congo DR': '🇨🇩', 'DR Congo': '🇨🇩', 'Croatia': '🇭🇷',
  'Curaçao': '🇨🇼', 'Curacao': '🇨🇼', 'Czechia': '🇨🇿', 'Czech Republic': '🇨🇿',
  'Ecuador': '🇪🇨', 'Egypt': '🇪🇬', 'England': '🏴󠁧󠁢󠁥󠁮󠁧󠁿', 'France': '🇫🇷',
  'Germany': '🇩🇪', 'Ghana': '🇬🇭', 'Haiti': '🇭🇹', 'Iran': '🇮🇷',
  'Iraq': '🇮🇶', 'Ivory Coast': '🇨🇮', "Côte d'Ivoire": '🇨🇮', 'Japan': '🇯🇵',
  'Jordan': '🇯🇴', 'Mexico': '🇲🇽', 'Morocco': '🇲🇦', 'Netherlands': '🇳🇱',
  'New Zealand': '🇳🇿', 'Norway': '🇳🇴', 'Panama': '🇵🇦', 'Paraguay': '🇵🇾',
  'Portugal': '🇵🇹', 'Qatar': '🇶🇦', 'Saudi Arabia': '🇸🇦', 'Scotland': '🏴󠁧󠁢󠁳󠁣󠁴󠁿',
  'Senegal': '🇸🇳', 'South Africa': '🇿🇦', 'South Korea': '🇰🇷', 'Spain': '🇪🇸',
  'Sweden': '🇸🇪', 'Switzerland': '🇨🇭', 'Tunisia': '🇹🇳', 'Turkey': '🇹🇷',
  'Türkiye': '🇹🇷', 'United States': '🇺🇸', 'Uruguay': '🇺🇾', 'Uzbekistan': '🇺🇿',
}

export function getFlag(name) {
  return FLAGS[name] ?? ''
}
