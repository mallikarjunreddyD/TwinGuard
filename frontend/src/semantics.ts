export const colors:Record<string,string>={red:'#ef6464',amber:'#eab85b',green:'#55bf98',unknown:'#8594a7'};
export function severity(trace:any){return trace?.assessment?.severity ?? 'unknown'}
export function safeText(value:unknown){return value==null?'unavailable':String(value)}
