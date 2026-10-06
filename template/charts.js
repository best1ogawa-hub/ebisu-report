const yen=v=>'¥'+Math.round(v).toLocaleString();
const NAVY='#1f3864',BLUE='#5b8fd1',RED='#c0392b',GREEN='#27ae60',ORANGE='#e08a1e',GRAY='#b9c2d0';
Chart.defaults.font.family='"Yu Gothic","Meiryo",sans-serif';Chart.defaults.font.size=11;
const noLeg={plugins:{legend:{display:false}}};
const mk=(id,c)=>new Chart(document.getElementById(id),c);
const adr=D.rev_cur.map((v,i)=>Math.round(v/D.rooms_cur[i])),pp=D.rev_cur.map((v,i)=>Math.round(v/D.ppl_cur[i]));
const pm=D.p_months;

mk('c_pace_amt',{type:'bar',data:{labels:pm,datasets:[
 {label:'OTB(現在)',data:D.p_sl_cur,backgroundColor:NAVY},
 {label:'前年同期',data:D.p_sl_py,backgroundColor:ORANGE},
 {label:'前年最終',data:D.p_sl_fin,backgroundColor:GRAY}]},
 options:{maintainAspectRatio:false,scales:{y:{ticks:{callback:v=>(v/1e6)+'M'}}}}});
mk('c_pace_rm',{type:'bar',data:{labels:pm,datasets:[
 {label:'OTB(現在)',data:D.p_rm_cur,backgroundColor:NAVY},
 {label:'前年同期',data:D.p_rm_py,backgroundColor:ORANGE},
 {label:'前年最終',data:D.p_rm_fin,backgroundColor:GRAY}]},options:{maintainAspectRatio:false}});

mk('c_yoy',{data:{labels:D.labels,datasets:[
 {type:'bar',label:'売上前年比',data:D.rev_yoy,backgroundColor:D.rev_yoy.map(v=>v<90?RED:(v<100?ORANGE:BLUE))},
 {type:'line',label:'100%',data:D.labels.map(_=>100),borderColor:'#888',borderDash:[6,4],pointRadius:0,borderWidth:1},
 {type:'line',label:'90%',data:D.labels.map(_=>90),borderColor:RED,borderDash:[3,3],pointRadius:0,borderWidth:1}]},
 options:{maintainAspectRatio:false,scales:{y:{ticks:{callback:v=>v+'%'}}}}});
mk('c_wkma',{type:'line',data:{labels:D.wk_labels,datasets:[
 {label:'受注金額(週)',data:D.wk_amt,borderColor:GRAY,pointRadius:0,borderWidth:1},
 {label:'4週移動平均',data:D.wk_amt_ma,borderColor:NAVY,pointRadius:0,borderWidth:2.5,tension:.3}]},
 options:{maintainAspectRatio:false,scales:{x:{ticks:{maxTicksLimit:10}},y:{ticks:{callback:v=>(v/1e6)+'M'}}}}});
mk('c_aov',{data:{labels:D.bk_mon,datasets:[
 {type:'bar',label:'平均単価',data:D.bk_aov,backgroundColor:BLUE,yAxisID:'y'},
 {type:'line',label:'キャンセル率',data:D.bk_canrate,borderColor:RED,yAxisID:'y1',tension:.3}]},
 options:{maintainAspectRatio:false,scales:{y:{position:'left',ticks:{callback:v=>yen(v)}},y1:{position:'right',grid:{drawOnChartArea:false},ticks:{callback:v=>v+'%'}}}}});

mk('c_rev',{data:{labels:D.labels,datasets:[{type:'bar',label:'売上',data:D.rev_cur,backgroundColor:NAVY,yAxisID:'y',order:2},{type:'line',label:'前年同月比',data:D.rev_yoy,borderColor:RED,backgroundColor:RED,yAxisID:'y1',tension:.3,order:1}]},options:{maintainAspectRatio:false,scales:{y:{position:'left',ticks:{callback:v=>(v/1e6)+'M'},title:{display:true,text:'売上(円)'}},y1:{position:'right',grid:{drawOnChartArea:false},ticks:{callback:v=>v+'%'},title:{display:true,text:'前年比'}}}}});
mk('c_rp',{type:'line',data:{labels:D.labels,datasets:[
 {label:'販売室数',data:D.rooms_cur,borderColor:BLUE,tension:.3},{label:'宿泊人数',data:D.ppl_cur,borderColor:ORANGE,tension:.3}]},options:{maintainAspectRatio:false}});
mk('c_occ',{type:'line',data:{labels:D.labels,datasets:[
 {label:'当年',data:D.occ_cur,borderColor:GREEN,backgroundColor:'rgba(39,174,96,.12)',fill:true,tension:.3},
 {label:'前年',data:D.occ_prev,borderColor:GRAY,borderDash:[5,4],tension:.3,pointRadius:0}]},options:{maintainAspectRatio:false,scales:{y:{min:50,max:100,ticks:{callback:v=>v+'%'}}}}});

const adrPrev=D.rev_prev.map((v,i)=>Math.round(v/D.rooms_prev[i]));
const adrYoY=adr.map((v,i)=>Math.round(v/adrPrev[i]*1000)/10);
mk('c_adr2',{data:{labels:D.labels,datasets:[
 {type:'bar',label:'ADR(当年)',data:adr,backgroundColor:NAVY,yAxisID:'y',order:2},
 {type:'line',label:'ADR前年同月比',data:adrYoY,borderColor:RED,backgroundColor:RED,yAxisID:'y1',tension:.3,order:1}]},
 options:{maintainAspectRatio:false,scales:{y:{position:'left',ticks:{callback:v=>yen(v)},title:{display:true,text:'ADR(円)'}},y1:{position:'right',grid:{drawOnChartArea:false},ticks:{callback:v=>v+'%'},title:{display:true,text:'前年比'}}}}});
const padrCur=D.p_rm_cur.map((r,i)=>r>0?Math.round(D.p_sl_cur[i]/r):null);
const padrPy=D.p_rm_py.map((r,i)=>r>0?Math.round(D.p_sl_py[i]/r):null);
const padrYoY=padrCur.map((v,i)=>(v&&padrPy[i])?Math.round(v/padrPy[i]*1000)/10:null);
mk('c_pace_adr',{data:{labels:D.p_months,datasets:[
 {type:'bar',label:'ADR OTB(現在)',data:padrCur,backgroundColor:NAVY,yAxisID:'y',order:3},
 {type:'bar',label:'ADR 前年同期',data:padrPy,backgroundColor:ORANGE,yAxisID:'y',order:2},
 {type:'line',label:'前年比',data:padrYoY,borderColor:RED,backgroundColor:RED,yAxisID:'y1',tension:.3,spanGaps:false,order:1}]},
 options:{maintainAspectRatio:false,scales:{y:{position:'left',ticks:{callback:v=>yen(v)},title:{display:true,text:'ADR(円)'}},y1:{position:'right',grid:{drawOnChartArea:false},ticks:{callback:v=>v+'%'},title:{display:true,text:'前年比'}}}}});

const bkYoY=D.bk_amt.map((v,i)=>(i>=12&&D.bk_amt[i-12])?Math.round(v/D.bk_amt[i-12]*1000)/10:null);
mk('c_bkmon',{data:{labels:D.bk_mon,datasets:[
 {type:'bar',label:'受注金額(総)',data:D.bk_amt,backgroundColor:BLUE,yAxisID:'y',order:2},
 {type:'line',label:'前年同月比',data:bkYoY,borderColor:RED,backgroundColor:RED,yAxisID:'y1',tension:.3,spanGaps:false,order:1}]},
 options:{maintainAspectRatio:false,scales:{y:{position:'left',ticks:{callback:v=>(v/1e6)+'M'},title:{display:true,text:'受注金額(円)'}},y1:{position:'right',grid:{drawOnChartArea:false},ticks:{callback:v=>v+'%'},title:{display:true,text:'前年同月比'}}}}});

function tbl(id,head,rows,foot){let h='<thead><tr>'+head.map(x=>'<th>'+x+'</th>').join('')+'</tr></thead><tbody>';
 h+=rows.map(r=>'<tr>'+r.map(c=>'<td>'+c+'</td>').join('')+'</tr>').join('')+'</tbody>';
 if(foot)h+='<tfoot><tr>'+foot.map(x=>'<td>'+x+'</td>').join('')+'</tr></tfoot>';document.getElementById(id).innerHTML=h;}
function jlabel(p){if(p===null)return '<span style="color:#888">時期尚早</span>';if(p<70)return '<span class="bad">✕ 大幅遅れ</span>';if(p<90)return '<span class="warn">△ やや遅れ</span>';if(p<100)return '<span class="good">○ ほぼ前年並み</span>';return '<span class="good">◎ 先行</span>';}
tbl('t_pace',['宿泊月','OTB室数','前年同期','前年最終','OTB売上','前年同期売上','前年最終売上','売上ペース','判定','不足額'],
 pm.map((m,i)=>[m,D.p_rm_cur[i],D.p_rm_py[i],D.p_rm_fin[i],yen(D.p_sl_cur[i]),yen(D.p_sl_py[i]),yen(D.p_sl_fin[i]),D.p_sl_pace[i]===null?'—':D.p_sl_pace[i]+'%',jlabel(D.p_sl_pace[i]),yen(D.p_gap_fin[i])]));
tbl('t_stay',['宿泊月','室数','人数','売上','稼働率','前年比','ADR','一人単価'],
 D.labels.map((m,i)=>[m,D.rooms_cur[i],D.ppl_cur[i],yen(D.rev_cur[i]),D.occ_cur[i]+'%',D.rev_yoy[i]+'%',yen(adr[i]),yen(pp[i])]),
 ['合計/平均',D.rooms_cur.reduce((a,b)=>a+b,0).toLocaleString(),D.ppl_cur.reduce((a,b)=>a+b,0).toLocaleString(),yen(D.rev_cur.reduce((a,b)=>a+b,0)),D.occ_avg+'%','-','-','-']);
