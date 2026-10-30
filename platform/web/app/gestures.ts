/** Fast swipes replay the path briefly; precise drags preserve the user's timing. */
export function dragDuration(elapsedMs:number, precise:boolean):number {
 return precise?Math.max(100,Math.min(1800,elapsedMs)):Math.max(80,Math.min(160,elapsedMs));
}
