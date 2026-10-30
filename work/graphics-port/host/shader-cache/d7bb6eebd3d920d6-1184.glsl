precision mediump float;

varying vec2 vTexCoord;
varying vec4 vColor;
varying vec2 vLineEquation;
varying float vLinePos;

uniform float u_lineThickness;
uniform float u_lineLength;

void main()
{
    float a = vLineEquation.x;
    float b = -1.;
    float c = vLineEquation.y;
    float distance = abs( a * gl_FragCoord.x + b * gl_FragCoord.y + c ) / sqrt( a*a + b*b ); // get the perpendicular distance to the line 
    float pixelSize = u_lineThickness/2.;
    
    if( abs(a) > 100000. ) // special treatment for vertical lines
        distance = abs(c-gl_FragCoord.x);
    
    distance = 1. - clamp( distance - pixelSize, 0., 1.); // we are interested in distance to the edge of the line, substract line thickness
    
    float linePos = abs(vLinePos); // get the position on the line, given in -length to +length space
    float capping = 1. - clamp( (linePos-u_lineLength)/u_lineThickness, 0., 1. ); // capping if we are left or right of the start or end point
    gl_FragColor = vec4(vColor.xyz, vColor.a * distance * capping  );
  
}