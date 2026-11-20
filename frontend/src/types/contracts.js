/** @typedef {{id:number,code:string,version:number,name:string,numerator:string,denominator:string,locked:boolean}} Metric */
/** @typedef {{id:number,class_code:string,day:string,mode:string,enrolled:number,attended:number,completed:number,refunds:number}} Fact */
/** @typedef {{id:number,metric_id:number,state:string,result:object,approval:string,note:string}} Snapshot */
/** @typedef {{id:number,class_code:string,state:string,note:string,facts_total:number,facts_removed:number,snapshots_total:number,snapshots_done:number,records_removed:number,remaining:number[],error:string,created_by:string,created:string,finished:string}} Cleanup */
