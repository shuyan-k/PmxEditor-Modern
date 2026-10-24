Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$pid_want = [int]$args[0]
$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $pid_want)
$wins = $root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)
foreach ($w in $wins) {
  $all = $w.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
  for ($i = 0; $i -lt $all.Count; $i++) {
    $e = $all.Item($i); $c = $e.Current; $r = $c.BoundingRectangle
    if ($r.Width -le 0) { continue }
    $n = $c.Name -replace "`t", " " -replace "`r?`n", "\\n"
    "{0}`t{1}`t{2}`t{3}`t{4}`t{5}`t{6}" -f $c.ControlType.ProgrammaticName.Replace("ControlType.",""), $n, [int]$r.X, [int]$r.Y, [int]$r.Width, [int]$r.Height, $c.AutomationId
  }
}
