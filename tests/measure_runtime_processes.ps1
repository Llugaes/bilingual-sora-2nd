# Requires PowerShell 7. Read-only counters; no game attachment or UI input.
# Use cumulative per-process CPU counters for steady windows with unchanged PIDs.
# A changing process tree needs per-PID deltas; it cannot use a last-minus-first sum.
#Requires -Version 7.0
param([Parameter(Mandatory)][string]$Root,[Parameter(Mandatory)][string]$Output,[int]$Seconds=120,[switch]$WithGame)
$ErrorActionPreference='Stop'
$rootPath=[IO.Path]::GetFullPath($Root).TrimEnd('\')+'\'
$outPath=[IO.Path]::GetFullPath($Output)
if(Test-Path -LiteralPath $outPath){throw 'Use a fresh measurement output'}
$timer=[Diagnostics.Stopwatch]::StartNew()
$lastCpu=@{}; $lastAt=0.0; $records=[Collections.Generic.List[object]]::new()
$writer=[IO.StreamWriter]::new($outPath,$false,[Text.UTF8Encoding]::new($false))
try {
 while($timer.Elapsed.TotalSeconds -lt $Seconds){
  $now=$timer.Elapsed.TotalSeconds; $rows=@(); $toolDelta=0.0; $gameDelta=0.0
  foreach($p in (Get-Process -ErrorAction SilentlyContinue)){
   if($p.ProcessName -notmatch 'BilingualSora|^python|^sora_2nd$'){continue}
   try{$path=$p.Path}catch{continue}
   $group=if($path -and $path.StartsWith($rootPath,[StringComparison]::OrdinalIgnoreCase)){'tool'}elseif($WithGame -and $p.ProcessName -eq 'sora_2nd'){'game'}else{continue}
   $cpu=$p.CPU; $key=[string]$p.Id; $delta=if($lastCpu.ContainsKey($key)){[math]::Max(0.0,[double]($cpu-$lastCpu[$key]))}else{0.0}
   $lastCpu[$key]=$cpu
   if($group -eq 'tool'){$toolDelta+=$delta}else{$gameDelta+=$delta}
   $rows+=@{pid=$p.Id;name=$p.ProcessName;group=$group;cpu_s=$cpu;private_mib=$p.PrivateMemorySize64/1MB;rss_mib=$p.WorkingSet64/1MB}
  }
  $elapsed=[math]::Max(.001,$now-$lastAt);$lastAt=$now
  $record=@{seconds=$now;at_utc=[DateTime]::UtcNow.ToString('o');tool_cpu_percent=100*$toolDelta/$elapsed/[Environment]::ProcessorCount;game_cpu_percent=100*$gameDelta/$elapsed/[Environment]::ProcessorCount;tool_private_mib=($rows|Where-Object group -eq 'tool'|Measure-Object private_mib -Sum).Sum;game_private_mib=($rows|Where-Object group -eq 'game'|Measure-Object private_mib -Sum).Sum;tool_rss_mib=($rows|Where-Object group -eq 'tool'|Measure-Object rss_mib -Sum).Sum;game_rss_mib=($rows|Where-Object group -eq 'game'|Measure-Object rss_mib -Sum).Sum;processes=$rows}
  $records.Add($record);$writer.WriteLine(($record|ConvertTo-Json -Depth 5 -Compress));$writer.Flush()
  Start-Sleep -Milliseconds 500
 }
}finally{$writer.Dispose()}
$summary=@{seconds=$timer.Elapsed.TotalSeconds;samples=$records.Count;logical_processors=[Environment]::ProcessorCount;root=$rootPath;with_game=[bool]$WithGame}
foreach($field in @('tool_cpu_percent','game_cpu_percent','tool_private_mib','game_private_mib','tool_rss_mib','game_rss_mib')){
 $values=@($records|ForEach-Object{$_[$field]}|Sort-Object);$summary[$field]=@{mean=($values|Measure-Object -Average).Average;peak=($values|Measure-Object -Maximum).Maximum;median=$values[[int]($values.Count/2)];last=$records[-1][$field]}
}
$summary|ConvertTo-Json -Depth 5|Set-Content -LiteralPath ($outPath+'.summary.json') -Encoding utf8
$summary|ConvertTo-Json -Depth 5 -Compress
