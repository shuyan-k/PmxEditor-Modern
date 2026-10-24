IPXBone b = bone[5];
System.Text.StringBuilder sb = new System.Text.StringBuilder();
try
{
    sb.AppendLine("links0=" + b.IK.Links.Count);
}
catch (Exception ex1) { sb.AppendLine("read err: " + ex1.GetType().Name); }
b.IsIK = true;
b.IK.Target = bone[6];
b.IK.LoopCount = 3;
b.IK.Angle = Q.D2R(10);
try
{
    if (b.IK.Links.Count > 0) b.IK.Links.Clear();
    var l1 = bdx.IKLink();
    l1.Bone = bone[4];
    l1.IsLimit = false;
    b.IK.Links.Add(l1);
    var l2 = bdx.IKLink();
    l2.Bone = bone[5];
    l2.IsLimit = false;
    b.IK.Links.Add(l2);
    sb.AppendLine("links1=" + b.IK.Links.Count);
}
catch (Exception ex2) { sb.AppendLine("link err: " + ex2.Message); }
System.IO.File.WriteAllText(@"D:\\Project\\PmxEditor_Modern\\tests\\parity\\cx_log.txt", sb.ToString() + "done", System.Text.Encoding.UTF8);
