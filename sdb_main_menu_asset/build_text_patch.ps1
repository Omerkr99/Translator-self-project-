$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$codec = @'
using System;
using System.Collections.Generic;
public static class MenuCodec {
    static int Key(byte[] d, int p) { return d[p] | d[p+1]<<8 | d[p+2]<<16 | d[p+3]<<24; }
    public static byte[] Encode(byte[] d) {
        var z = new List<byte>(); var map = new Dictionary<int,List<int>>();
        int i=0, lit=-1;
        Action flush = () => { if(lit<0)return; int p=lit,n=i-lit; while(n>0){int q=Math.Min(128,n);z.Add((byte)(q-1));for(int x=0;x<q;x++)z.Add(d[p+x]);p+=q;n-=q;}lit=-1; };
        while(i<d.Length){
            int best=0,type=0,arg=0,rep=1;
            while(rep<66 && i+rep<d.Length && d[i+rep]==d[i]) rep++;
            if(rep>=3){best=rep;type=1;}
            if(i+3<d.Length){
                int delta=(d[i+1]-d[i])&255, inc=2;
                if(delta!=0){while(inc<19&&i+inc<d.Length&&d[i+inc]==(byte)(d[i]+inc*delta))inc++;if(inc>=4&&inc>best){best=inc;type=2;arg=delta;}}
                List<int> list;
                if(map.TryGetValue(Key(d,i),out list)) for(int q=list.Count-1;q>=0;q--){int p=list[q],off=i-p;if(off>65535)break;int n=4;while(n<35&&i+n<d.Length&&d[p+n]==d[i+n])n++;if(n>best){best=n;type=3;arg=off;if(n==35)break;}}
            }
            if(best>0){
                flush();
                if(type==1){z.Add((byte)(best+125));z.Add(d[i]);}
                else if(type==2){z.Add((byte)(best+220));z.Add((byte)arg);z.Add(d[i]);}
                else {z.Add((byte)(best+188));z.Add((byte)(arg>>8));z.Add((byte)arg);}
                int end=i+best; for(int p=i;p<end;p++) if(p+3<d.Length){int k=Key(d,p);List<int> l;if(!map.TryGetValue(k,out l)){l=new List<int>();map[k]=l;}l.Add(p);} i=end;
            } else {
                if(lit<0)lit=i; if(i+3<d.Length){int k=Key(d,i);List<int> l;if(!map.TryGetValue(k,out l)){l=new List<int>();map[k]=l;}l.Add(i);} i++; if(i-lit==128)flush();
            }
        }
        flush(); z.Add(255); return z.ToArray();
    }
}
'@
Add-Type -TypeDefinition $codec

function Decode-Stream([byte[]] $src, [int] $start) {
    $out = [Collections.Generic.List[byte]]::new(); $i = $start
    while ($i -lt $src.Length) {
        $c = $src[$i++]
        if ($c -eq 255) { break }
        if ($c -lt 128) { $n=$c+1; for($k=0;$k-lt$n;$k++){$out.Add($src[$i++])} }
        elseif ($c -lt 192) { $n=$c-125;$v=$src[$i++];for($k=0;$k-lt$n;$k++){$out.Add($v)} }
        elseif ($c -lt 224) { $n=$c-188;$off=$src[$i]*256+$src[$i+1];$i+=2;$p=$out.Count-$off;for($k=0;$k-lt$n;$k++){$out.Add($out[$p+$k])} }
        elseif ($c -lt 240) { $n=$c-220;$d=$src[$i++];$v=$src[$i++];for($k=0;$k-lt$n;$k++){$out.Add(($v+$k*$d)-band 255)} }
        else { throw "Invalid codec byte $c" }
    }
    [pscustomobject]@{ Data=$out.ToArray(); Consumed=$i-$start }
}

function Expand-Exactly([byte[]] $encoded, [int] $target) {
    if ($encoded.Length -gt $target) { throw "Encoded stream $($encoded.Length) exceeds $target" }
    $need=$target-$encoded.Length
    if($need-eq0){return $encoded}
    $tokens=@();$decoded=[Collections.Generic.List[byte]]::new();$i=0
    while($i-lt$encoded.Length){
        $st=$i;$os=$decoded.Count;$c=$encoded[$i++] 
        if($c-eq255){$tokens+=,[pscustomobject]@{Start=$st;InLen=1;OutStart=$os;OutLen=0;Growth=0};break}
        if($c-lt128){$n=$c+1;for($k=0;$k-lt$n;$k++){$decoded.Add($encoded[$i++])}}
        elseif($c-lt192){$n=$c-125;$v=$encoded[$i++];for($k=0;$k-lt$n;$k++){$decoded.Add($v)}}
        elseif($c-lt224){$n=$c-188;$off=$encoded[$i]*256+$encoded[$i+1];$i+=2;$p=$decoded.Count-$off;for($k=0;$k-lt$n;$k++){$decoded.Add($decoded[$p+$k])}}
        else{$n=$c-220;$d=$encoded[$i++];$v=$encoded[$i++];for($k=0;$k-lt$n;$k++){$decoded.Add(($v+$k*$d)-band255)}}
        $tokens+=,[pscustomobject]@{Start=$st;InLen=$i-$st;OutStart=$os;OutLen=$n;Growth=$n+1-($i-$st)}
    }
    $ways=@{0=@()}
    for($ti=0;$ti-lt$tokens.Count;$ti++){
        $g=$tokens[$ti].Growth;if($g-le0){continue}
        foreach($s in @($ways.Keys|Sort-Object -Descending)){$ns=[int]$s+$g;if($ns-le$need-and-not$ways.ContainsKey($ns)){$ways[$ns]=@($ways[$s])+$ti}}
        if($ways.ContainsKey($need)){break}
    }
    if(-not$ways.ContainsKey($need)){throw "Cannot expand by exactly $need"}
    $chosen=@{};foreach($x in $ways[$need]){$chosen[[int]$x]=$true}
    $fixed=[Collections.Generic.List[byte]]::new()
    for($ti=0;$ti-lt$tokens.Count;$ti++){$t=$tokens[$ti];if($chosen.ContainsKey($ti)){$fixed.Add([byte]($t.OutLen-1));for($k=0;$k-lt$t.OutLen;$k++){$fixed.Add($decoded[$t.OutStart+$k])}}else{for($k=0;$k-lt$t.InLen;$k++){$fixed.Add($encoded[$t.Start+$k])}}}
    if($fixed.Count-ne$target){throw "Expansion produced $($fixed.Count), expected $target"}
    $fixed.ToArray()
}

$root = $PSScriptRoot
$originalBytes = [IO.File]::ReadAllBytes((Join-Path $root 'PROGDAT.BIN'))
$originalPng = [Drawing.Bitmap]::FromFile((Join-Path $root 'PROGDAT_group_0.png'))
$previewPng = [Drawing.Bitmap]::FromFile((Join-Path $root 'PROGDAT_translated_with_gcrts_320x240.png'))
$cursor=0;$streams=@();$report=@()
for($strip=0;$strip-lt5;$strip++){
    $decoded=Decode-Stream $originalBytes $cursor;$data=$decoded.Data;$originalSize=$decoded.Consumed
    $darkIndex=0;$darkScore=999
    for($idx=0;$idx-lt256;$idx++){$v=[BitConverter]::ToUInt16($data,20+$idx*2);$score=($v-band31)+(($v-shr5)-band31)+(($v-shr10)-band31);if($score-lt$darkScore){$darkScore=$score;$darkIndex=$idx}}
    for($y=0;$y-lt240;$y++){for($x=0;$x-lt64;$x++){$gx=$strip*64+$x;$a=$originalPng.GetPixel($gx,$y);$b=$previewPng.GetPixel($gx,$y);if($a.ToArgb()-ne$b.ToArgb()){$bright=$b.R+$b.G+$b.B;if($bright-ge384){$data[544+$y*64+$x]=1}}}}
    $encoded=[MenuCodec]::Encode($data);$exact=Expand-Exactly $encoded $originalSize
    $check=Decode-Stream $exact 0
    if(-not[Linq.Enumerable]::SequenceEqual([byte[]]$data,[byte[]]$check.Data)){throw "Round trip failed for strip $strip"}
    $streams+=,$exact;$report+=,[pscustomobject]@{Strip=$strip;Offset=('0x{0:X}'-f$cursor);Original=$originalSize;Encoded=$encoded.Length;Exact=$exact.Length;DarkIndex=$darkIndex}
    $cursor+=$originalSize
}
$originalPng.Dispose();$previewPng.Dispose()
$result=[byte[]]::new($originalBytes.Length);$pos=0
foreach($stream in $streams){[Array]::Copy($stream,0,$result,$pos,$stream.Length);$pos+=$stream.Length}
[Array]::Copy($originalBytes,$cursor,$result,$cursor,$originalBytes.Length-$cursor)
$outPath=Join-Path $root 'PROGDAT_translated_with_gcrts_exact.BIN'
[IO.File]::WriteAllBytes($outPath,$result)
$report|Format-Table -AutoSize
Get-FileHash $outPath -Algorithm SHA256
