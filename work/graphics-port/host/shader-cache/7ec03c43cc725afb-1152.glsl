precision mediump float;


uniform sampler2D tex2;


varying highp vec3 _reflectDir;
varying mediump vec2 _varCoord;
varying highp vec3 _viewDirection;

varying highp vec3 _normal;

varying mediump float _vertexColor;


float saturate(float x)
{
	return clamp(x, 0., 1.);
}


void main()
{
	vec4 ambientColor = vec4(0.1, 0.1, 0.1, 0);
	vec4 diffuseColor  = vec4(0.6,0.6,0.6, 1) ;
	vec4 diffuseColor2 = vec4(0.0,0.0,0.0, 1.) ;
	vec4 specularColor = vec4(0.7,0.7,0.7, 1.) ;
	float shininess = 0.8;      
	
	// fresnel factor between two diffuse colors
	float fresnelColorShininess = 8.0;

	// scaling of vertex colors (targetColor = (color+brightness)*contrast
	float vertexColorBrightness = 1.0;
	float vertexColorContrast = 1.0;
	
	// texture does is upside down
	vec2 varCoord = _varCoord;
	varCoord.y = 1.0 - varCoord.y;
	
	float normalAlpha = 1.0;

	vec3 normal = _normal;
	
	vec4 paintColor = ambientColor;
	
	float NdotV = saturate(dot(normal, _viewDirection));
	float h = pow(NdotV, fresnelColorShininess);
	vec4 diffColor = diffuseColor*h + diffuseColor2*(1.0-h);
	
	vec3 rt = _reflectDir.xzy;
 	rt.y = rt.y-0.8;
 	rt.x = rt.x+0.2;
 	vec2 reflectTexCoord = (rt.xy * 0.5 + 0.5);
 	vec4 incomeLight = texture2D(tex2, reflectTexCoord) * shininess;
	paintColor += incomeLight * specularColor + diffColor;
	//paintColor = vec4(reflectTexCoord, 0., 1.);//
	
	// scale the vertex color
	float vertexColor = _vertexColor;
	vertexColor = saturate((vertexColor+vertexColorBrightness)*vertexColorContrast);

						  
	paintColor = paintColor * vertexColor;
	
	paintColor.w *= normalAlpha;
	
	gl_FragColor = paintColor;
} 
