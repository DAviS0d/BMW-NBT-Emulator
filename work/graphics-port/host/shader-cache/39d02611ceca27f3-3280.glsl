precision mediump float;

uniform mediump vec2 pdcValue0;
uniform mediump vec2 pdcValue1;
uniform mediump vec2 pdcValue2;
uniform mediump vec2 pdcValue3;
uniform mediump vec2 pdcValue4;
uniform mediump vec2 pdcValue5;
uniform mediump vec2 pdcValue6;
uniform mediump vec2 pdcValue7;
uniform mediump vec2 pdcValue8;
uniform mediump vec2 pdcValue9;
uniform mediump vec2 pdcValue10;
uniform mediump vec2 pdcValue11;
const int numPdcValues = 8;

uniform sampler2D tex0;

varying mediump vec2 vTexCoord;
varying mediump vec2 vTexCoordRotated;

int clampInt(int value, int minValue, int maxValue)
{
    return (value>minValue) ? ((value<maxValue)?value:maxValue) : minValue;
}

float clampFloat(float value, float minValue, float maxValue)
{
    return (value>minValue) ? ((value<maxValue)?value:maxValue) : minValue;
}

vec2 calcSpline(vec4 xCoeffs, vec4 yCoeffs, float t)
{
	float splineParam = 2.0;

    float t2 = t * t;
    float t3 = t * t * t;


    vec2 result= vec2( ( (xCoeffs.x*t3 + xCoeffs.y*t2 + xCoeffs.z*t + xCoeffs.w) / splineParam ), 
                 	   ( (yCoeffs.x*t3 + yCoeffs.y*t2 + yCoeffs.z*t + yCoeffs.w) / splineParam ) );

    return result;
}

float findSplinePos(float xCoord, out vec4 xCoeffs, out vec4 yCoeffs)
{
    vec2 pdcValues[numPdcValues+4];
    
    pdcValues[0] = vec2(0., pdcValue0.y);
    pdcValues[1] = vec2(pdcValue0.x, pdcValue0.y);
    pdcValues[2] = vec2(pdcValue1.x, pdcValue0.y);
	pdcValues[3] = vec2(pdcValue2.x, pdcValue1.y);
	pdcValues[4] = vec2(pdcValue3.x, pdcValue2.y);
	pdcValues[5] = vec2(pdcValue4.x, pdcValue3.y);
	pdcValues[6] = vec2(pdcValue5.x, pdcValue4.y);
	pdcValues[7] = vec2(pdcValue6.x, pdcValue5.y);
	pdcValues[8] = vec2(pdcValue7.x, pdcValue6.y);
    pdcValues[9] = vec2(1., pdcValue7.y);
    pdcValues[10] = vec2(1., pdcValue7.y);
    pdcValues[11] = vec2(1., pdcValue7.y);
    
    mat4 splineMatrix = mat4(	-1.,  3., -3.,  1.,
                             2., -5.,  4., -1.,
                            -1.,  0.,  1.,  0.,
                             0.,  2.,  0.,  0. );
   
    float position = 0.;
    int i = 0;
    while(i <= numPdcValues)
    {
        if( xCoord > pdcValues[i].x && xCoord <= pdcValues[i+1].x )
        {
            float length = pdcValues[i+1].x - pdcValues[i].x;
            position = (((xCoord - pdcValues[i].x) / length) + float(i-1) ) / float(numPdcValues-1);
                    
            vec2 nm1 = vec2(pdcValues[i  ].x, 1.-pdcValues[i  ].y);
            vec2 n   = vec2(pdcValues[i+1].x, 1.-pdcValues[i+1].y);
            vec2 np1 = vec2(pdcValues[i+2].x, 1.-pdcValues[i+2].y);
            vec2 np2 = vec2(pdcValues[i+3].x, 1.-pdcValues[i+3].y);

            vec4 xVec = vec4( nm1.x, n.x, np1.x, np2.x);
            vec4 yVec = vec4( nm1.y, n.y, np1.y, np2.y);

            xCoeffs = xVec*splineMatrix;
            yCoeffs = yVec*splineMatrix;
        }
        i++;
    }
    
    return position;
}

void main(){
	
    vec4 xCoeffs = vec4(0., 0., 0., 0.);
	vec4 yCoeffs = vec4(0., 0., 0., 0.);
    
    float splineParamPos = findSplinePos(vTexCoordRotated.x, xCoeffs, yCoeffs);
    
	int iN = int(splineParamPos * float(numPdcValues-1));
	float t = splineParamPos*float(numPdcValues-1) - float(iN);


 	//computeCoeffs(iN, xCoeffs, yCoeffs);

	vec2 splinePos = calcSpline(xCoeffs, yCoeffs, t);
    
	vec4 texColor = texture2D(tex0, vec2(vTexCoord.x, vTexCoord.y));
	
	gl_FragColor = vec4( texColor.xyz, texColor.a * clampFloat((splinePos.y - vTexCoordRotated.y)*100., 0., 1.) ); 
	
	//gl_FragColor = vec4( vTexCoordRotated , splinePos.y, 1.0);
    //gl_FragColor = vec4(0., 1., 0., 1.);
}
