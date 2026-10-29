export const colors:Record<string,string>={red:'#a43d35',amber:'#91601f',green:'#3d7258',unknown:'#74828a'};
export function severity(trace:any){return trace?.assessment?.severity ?? 'unknown'}
export function safeText(value:unknown){return value==null?'unavailable':String(value)}
