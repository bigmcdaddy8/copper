# Chris Drysdale VWAP Wave System (Native Code)
declare upper;

input dev1 = 1.0;
input dev2 = 2.0;

# Check for a new trading day reset
def isNewDay = GetDay() != GetDay()[1];

# Natively calculate the volume-weighted sums
def volumeSum = if isNewDay then volume else volumeSum[1] + volume;
def volumeVwapSum = if isNewDay then volume * vwap else volumeVwapSum[1] + volume * vwap;
def volumeVwap2Sum = if isNewDay then volume * Sqr(vwap) else volumeVwap2Sum[1] + volume * Sqr(vwap);

# Core VWAP Line
plot vwapValue = volumeVwapSum / volumeSum;

# Calculate the actual standard deviation variance
def variance = Max(volumeVwap2Sum / volumeSum - Sqr(vwapValue), 0);
def deviation = Sqrt(variance);

# Plot the 1st Standard Deviation Bands (The Value Area)
plot bandUpper1 = vwapValue + (dev1 * deviation);
plot bandLower1 = vwapValue - (dev1 * deviation);

# Plot the 2nd Standard Deviation Bands
plot bandUpper2 = vwapValue + (dev2 * deviation);
plot bandLower2 = vwapValue - (dev2 * deviation);

# Formatting and Style Guide
vwapValue.SetDefaultColor(Color.YELLOW);
vwapValue.SetStyle(Curve.SHORT_DASH);
vwapValue.SetLineWeight(2);

bandUpper1.SetDefaultColor(Color.GRAY);
bandLower1.SetDefaultColor(Color.GRAY);

bandUpper2.SetDefaultColor(Color.RED);
bandLower2.SetDefaultColor(Color.RED);

# Shading the Value Area Light Gray
AddCloud(bandUpper1, bandLower1, Color.LIGHT_GRAY, Color.LIGHT_GRAY);

